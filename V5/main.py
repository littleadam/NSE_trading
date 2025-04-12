# main.py
import os
import time
import signal
import schedule
from datetime import datetime, time as dt_time
from config import CHECK_INTERVAL, TRADE_DAYS, LOT_SIZE
from auth.kite_auth import KiteSession
from core.strategy import NiftyStrategy
from core.order_manager import OrderManager
from core.risk_manager import RiskManager
from core.streaming import DataStream
from utils.helpers import is_trading_day, get_instrument_tokens
from utils.logger import configure_logging

configure_logging()

class TradingApp:
    def __init__(self):
        self.kite = KiteSession().connect()
        self.order_manager = OrderManager(self.kite)
        self.risk_manager = RiskManager(self.kite)
        self.strategy = None
        self.stream = None
        self.running = False

    def initialize(self):
        # Fetch required instrument tokens
        instruments = get_instrument_tokens(self.kite)
        self.stream = DataStream(
            api_key=os.getenv('KITE_API_KEY'),
            access_token=self.kite.access_token,
            instruments=instruments
        )
        self.stream.connect()
        
        # Wait for initial price update
        while not self.stream.spot_price:
            time.sleep(1)
        
        self.strategy = NiftyStrategy(self.kite, self.stream.spot_price)
        logger.info("Trading app initialized")

    def _execute_strategy_checks(self):
        try:
            if not self._should_run():
                return

            if self.risk_manager.check_shutdown_triggers():
                logger.critical("Shutdown trigger activated!")
                self.risk_manager.execute_emergency_shutdown()
                return

            if config.STRADDLE_FLAG:
                self._manage_strategy('STRADDLE')
            if config.STRANGLE_FLAG:
                self._manage_strategy('STRANGLE')

        except Exception as e:
            logger.error(f"Strategy check failed: {str(e)}", exc_info=True)

    def _manage_strategy(self, strategy_type):
        if not self.order_manager.check_existing_positions(strategy_type):
            strikes = self.strategy.calculate_strikes(strategy_type)
            self.order_manager.place_strategy_orders(strategy_type, strikes)
        else:
            self.order_manager.check_profit_triggers(strategy_type)

    def _should_run(self):
        now = datetime.now()
        if now.strftime('%a') not in TRADE_DAYS:
            return False
        if not is_trading_day(now.date()):
            return False
        current_time = now.time()
        return dt_time(9, 15) <= current_time <= dt_time(15, 30)

    def run(self):
        self.running = True
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)

        schedule.every(CHECK_INTERVAL).seconds.do(self._execute_strategy_checks)
        
        logger.info("Starting trading loop...")
        while self.running:
            schedule.run_pending()
            time.sleep(1)

    def shutdown(self, signum=None, frame=None):
        logger.info("Shutting down...")
        self.running = False
        self.stream.disconnect()
        schedule.clear()
        logger.info("Cleanup completed")

if __name__ == "__main__":
    app = TradingApp()
    app.initialize()
    app.run()
