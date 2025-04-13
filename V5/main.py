# main.py
import time
import schedule
import logging
from datetime import datetime, time as dt_time
from typing import Dict, List

from config import Config as config
from auth.kite_auth import KiteAuth
from core.strategy import OptionsStrategy
from core.order_manager import OrderManager
from core.risk_manager import RiskManager
from core.expiry_manager import ExpiryManager
from core.streaming import DataStream
from utils.helpers import Helpers
from utils.logger import setup_logger

setup_logger()
logger = logging.getLogger(__name__)

class NiftyOptionsTrading:
    def __init__(self):
        self.kite = self._initialize_kite()
        self.order_manager = OrderManager(self.kite)
        self.risk_manager = RiskManager(self.kite)
        self.data_stream = DataStream(
            self.kite, 
            config.KITE_API_KEY,
            config.KITE_ACCESS_TOKEN
        )
        self.expiry_manager = ExpiryManager(
            self.kite,
            self.order_manager,
            self.data_stream.get_spot_price()
        )
        self.current_positions: Dict = {}

    def _initialize_kite(self):
        try:
            auth = KiteAuth()
            return auth.authenticate()
        except Exception as e:
            logger.error(f"Authentication failed: {str(e)}")
            raise

    def _market_time_check(self) -> bool:
        now = datetime.now()
        if not config.TRADING_CALENDAR.is_trading_day(now.date()):
            logger.info("Non-trading day")
            return False
            
        current_time = now.time()
        if not (dt_time(9, 15) <= current_time <= dt_time(15, 30)):
            logger.info("Outside market hours")
            return False
            
        return True

    def _get_spot_price(self) -> float:
        return self.data_stream.get_spot_price()

    def _execute_strategy(self, strategy_type: str, spot_price: float):
        try:
            if self.order_manager._check_existing_positions(strategy_type, 0, ""):
                logger.info(f"Existing {strategy_type} positions found")
                return

            strategy = OptionsStrategy(self.kite, spot_price)
            params = strategy.get_strategy_parameters(
                strategy_type,
                self.expiry_manager.current_far_expiry['far_month']
            )
            
            instruments = self.expiry_manager.get_instruments(
                strategy_type,
                params['ce'],
                params['pe'],
                config.FAR_SELL_ADD
            )
            
            for instrument in instruments:
                self.order_manager.place_order(
                    strategy_type,
                    instrument['strike'],
                    instrument['expiry'],
                    config.LOT_SIZE
                )

            logger.info(f"{strategy_type} strategy executed")
            
        except Exception as e:
            logger.error(f"Strategy execution failed: {str(e)}")
            self.risk_manager.execute_emergency_shutdown()

    def _run_strategies(self):
        if not self._market_time_check():
            return

        try:
            spot_price = self._get_spot_price()
            self.current_positions = self.kite.positions()
            
            if self.risk_manager.check_shutdown_triggers():
                logger.critical("Shutdown triggers activated!")
                self.risk_manager.execute_emergency_shutdown()
                return

            if config.STRADDLE_FLAG:
                self._execute_strategy("STRADDLE", spot_price)
                
            if config.STRANGLE_FLAG:
                self._execute_strategy("STRANGLE", spot_price)
                
            self._manage_hedges(spot_price)
            
        except Exception as e:
            logger.error(f"Main execution error: {str(e)}")

    def _manage_hedges(self, spot_price: float):
        try:
            if config.BUY_HEDGE:
                hedge_instruments = self.expiry_manager.get_hedge_instruments(
                    spot_price,
                    config.ADJACENCY_GAP
                )
                for inst in hedge_instruments:
                    qty = config.LOT_SIZE if config.HEDGE_ONE_LOT else self._calculate_hedge_qty()
                    self.order_manager.place_order(
                        "HEDGE",
                        inst['strike'],
                        inst['expiry'],
                        qty
                    )
        except Exception as e:
            logger.error(f"Hedge management failed: {str(e)}")

    def _calculate_hedge_qty(self) -> int:
        try:
            positions = self.kite.positions()["net"]
            sell_qty = sum(
                p["quantity"] for p in positions
                if p["product"] == "MIS" and p["quantity"] < 0
            )
            return abs(sell_qty) // 2
        except Exception as e:
            logger.error(f"Hedge qty calculation failed: {str(e)}")
            return config.LOT_SIZE

    def start_streaming(self):
        instruments = [self.data_stream.nifty_token]
        if config.FAR_SELL_ADD:
            far_instruments = self.expiry_manager.get_instruments(
                "STRADDLE",
                self.data_stream.get_spot_price(),
                self.data_stream.get_spot_price(),
                True
            )
            instruments.extend([inst['token'] for inst in far_instruments])
        self.data_stream.start_stream(instruments)

    def run(self):
        logger.info("Starting Nifty Options Trading System")
        self.start_streaming()
        
        schedule.every(config.CHECK_INTERVAL).seconds.do(self._run_strategies)
        
        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down gracefully...")
        finally:
            self.data_stream.stop()

if __name__ == "__main__":
    try:
        trading_system = NiftyOptionsTrading()
        trading_system.run()
    except Exception as e:
        logging.critical(f"System crash: {str(e)}")
        raise
