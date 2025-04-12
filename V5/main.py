# main.py
import time
import schedule
import logging
from datetime import datetime, time as dt_time
from typing import Dict, List, Optional

from config import Config
from auth.kite_auth import KiteAuth
from core.strategy import OptionsStrategy
from core.order_manager import OrderManager
from core.risk_manager import RiskManager
from core.expiry_manager import ExpiryManager
from core.streaming import DataStream
from utils.logger import setup_logger

class NiftyOptionsTrading:
    def __init__(self):
        setup_logger()
        self.logger = logging.getLogger(__name__)
        self.kite = self._initialize_kite()
        self.order_manager = OrderManager(self.kite)
        self.risk_manager = RiskManager(self.kite)
        self.expiry_manager = None  # Initialize after spot price is available
        self.data_stream: Optional[DataStream] = None
        self.current_positions: Dict = {}
        self.spot_price: Optional[float] = None

    def _initialize_kite(self):
        try:
            auth = KiteAuth()
            return auth.get_kite()
        except Exception as e:
            self.logger.error(f"Authentication failed: {str(e)}")
            raise

    def _market_time_check(self) -> bool:
        now = datetime.now()
        current_date = now.date()
        
        # Check trading days and market hours
        if not Config.TRADING_CALENDAR.is_trading_day(current_date):
            self.logger.info("Non-trading day")
            return False
            
        current_time = now.time()
        if not (dt_time(9, 15) <= current_time <= dt_time(15, 30)):
            self.logger.info("Outside market hours")
            return False
            
        return True

    def _get_spot_price(self) -> float:
        try:
            nifty_quote = self.kite.quote("NSE:NIFTY 50")
            self.spot_price = nifty_quote["last_price"]
            
            # Initialize expiry manager after first spot price fetch
            if not self.expiry_manager:
                self.expiry_manager = ExpiryManager(
                    self.kite, 
                    self.order_manager,
                    self.spot_price
                )
                
            return self.spot_price
        except Exception as e:
            self.logger.error(f"Spot price fetch failed: {str(e)}")
            raise

    def _execute_strategy(self, strategy_type: str, spot_price: float):
        try:
            # Conflict check
            if self.order_manager._check_existing_positions(strategy_type, 0, ""):
                self.logger.info(f"Existing {strategy_type} positions found")
                return

            strategy = OptionsStrategy(self.kite, spot_price)
            params = strategy.get_strategy_parameters(strategy_type, strategy.get_far_expiry())
            
            # Get instruments from expiry manager
            instruments = self.expiry_manager.get_instruments(
                strategy_type,
                params['ce'],
                params['pe'],
                Config.FAR_SELL_ADD
            )
            
            # Place orders
            order_ids = []
            for inst in instruments:
                result = self.order_manager.place_order(
                    strategy_type,
                    inst['strike'],
                    inst['expiry'],
                    Config.LOT_SIZE
                )
                if result:
                    order_ids.extend(result)

            self.logger.info(f"{strategy_type} strategy executed. Orders: {order_ids}")
            
        except Exception as e:
            self.logger.error(f"Strategy execution failed: {str(e)}")
            self.risk_manager.execute_emergency_shutdown()

    def _run_strategies(self):
        if not self._market_time_check():
            return

        try:
            spot_price = self._get_spot_price()
            self.current_positions = self.kite.positions()
            
            if self.risk_manager.check_shutdown_triggers():
                self.logger.critical("Shutdown triggers activated!")
                self.risk_manager.execute_emergency_shutdown()
                return

            if Config.STRADDLE_FLAG:
                self._execute_strategy("STRADDLE", spot_price)
                
            if Config.STRANGLE_FLAG:
                self._execute_strategy("STRANGLE", spot_price)
                
            self._manage_hedges(spot_price)
            
        except Exception as e:
            self.logger.error(f"Main execution error: {str(e)}")

    def _manage_hedges(self, spot_price: float):
        try:
            if Config.BUY_HEDGE:
                hedge_instruments = self.expiry_manager.get_hedge_instruments(
                    spot_price,
                    Config.ADJACENCY_GAP
                )
                for inst in hedge_instruments:
                    qty = Config.LOT_SIZE if Config.HEDGE_ONE_LOT else self._calculate_hedge_qty()
                    self.order_manager.place_order(
                        "HEDGE",
                        inst['strike'],
                        inst['expiry'],
                        qty
                    )
        except Exception as e:
            self.logger.error(f"Hedge management failed: {str(e)}")

    def _calculate_hedge_qty(self) -> int:
        try:
            positions = self.kite.positions()["net"]
            sell_qty = sum(
                p["quantity"] for p in positions
                if p["product"] == "MIS" and p["quantity"] < 0
            )
            return abs(sell_qty) // 2
        except Exception as e:
            self.logger.error(f"Hedge qty calculation failed: {str(e)}")
            return Config.LOT_SIZE

    def start_streaming(self):
        self.data_stream = DataStream(
            self.kite,
            Config.KITE_API_KEY,
            Config.KITE_ACCESS_TOKEN
        )
        self.data_stream.start_stream()
        
        # Subscribe to NIFTY and strategy instruments
        tokens = [self.data_stream.nifty_token]
        if self.expiry_manager:
            tokens.extend(self.expiry_manager.get_active_tokens())
        self.data_stream.subscribe(tokens)

    def run(self):
        self.logger.info("Starting Nifty Options Trading System")
        self.start_streaming()
        
        schedule.every(Config.CHECK_INTERVAL).seconds.do(self._run_strategies)
        
        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Shutting down gracefully...")
        finally:
            if self.data_stream:
                self.data_stream.stop()

if __name__ == "__main__":
    try:
        trading_system = NiftyOptionsTrading()
        trading_system.run()
    except Exception as e:
        logging.critical(f"System crash: {str(e)}")
        raise
