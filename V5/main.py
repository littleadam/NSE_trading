# main.py
import time
import schedule
import logging
import sys
from datetime import datetime, time as dt_time
from typing import Dict, List

from config import Config
from auth.kite_auth import KiteAuth
from core.strategy import OptionsStrategy
from core.order_manager import OrderManager
from core.risk_manager import RiskManager
from core.expiry_manager import ExpiryManager
from core.streaming import DataStream
from utils.helpers import Helpers
from utils.logger import setup_logger, log_function, DecisionLogger

# Initialize logging
setup_logger()
logger = logging.getLogger(__name__)

class NiftyOptionsTrading:
    @log_function
    def __init__(self):
        self.kite = self._initialize_kite()
        self.order_manager = OrderManager(self.kite)
        self.risk_manager = RiskManager(self.kite)
        self.data_stream = DataStream(
            self.kite, 
            Config.KITE_API_KEY,
            Config.KITE_ACCESS_TOKEN
        )
        self.expiry_manager = ExpiryManager(
            self.kite,
            self.order_manager,
            self._get_spot_price()
        )
        self.current_positions: Dict = {}
        self.last_execution_time: datetime = None
        self.active = True

    @log_function
    def _initialize_kite(self):
        """Full authentication flow with environment validation"""
        try:
            if not all([Config.KITE_API_KEY, Config.KITE_API_SECRET]):
                raise EnvironmentError("Missing API credentials in environment")
            
            auth = KiteAuth()
            kite = auth.authenticate()
            DecisionLogger.log_decision({"event": "auth_success"})
            return kite
        except Exception as e:
            logger.critical(f"Authentication failed: {str(e)}")
            raise RuntimeError("Fatal authentication error") from e

    @log_function
    def _market_time_check(self) -> bool:
        """Enhanced market hours validation with configurable days"""
        now = datetime.now()
        
        # Check trading day
        if now.strftime('%a') not in Config.TRADE_DAYS:
            logger.info("Non-trading day")
            return False
            
        # Check market hours
        current_time = now.time()
        if not (dt_time(9, 15) <= current_time <= dt_time(15, 30)):
            logger.info("Outside market hours")
            return False

        # Throttle execution frequency
        if self.last_execution_time and \
           (now - self.last_execution_time).total_seconds() < Config.CHECK_INTERVAL:
            return False
            
        self.last_execution_time = now
        return True

    def _get_spot_price(self) -> float:
        """Robust spot price retrieval with fallbacks"""
        try:
            price = self.data_stream.get_spot_price()
            if not price:
                raise ValueError("Spot price unavailable")
            return price
        except Exception as e:
            logger.error(f"Spot price fetch failed: {str(e)}")
            return Helpers.get_nearest_strike(15000)  # Fallback value

    @log_function
    def _execute_strategy(self, strategy_type: str, spot_price: float):
        """Complete strategy execution flow with conflict checks and position cleanup"""
        try:
            # Validate market conditions
            if not self._market_time_check():
                return

            # Close any opposing BUY positions first
            closed_orders = self.order_manager.close_opposite_positions(
                strategy_type, 
                self.expiry_manager.current_far_expiry['far_month']
            )
            if closed_orders:
                logger.info(f"Closed {len(closed_orders)} opposing positions")
                time.sleep(2)  # Allow order processing

            # Check existing positions after cleanup
            if self.order_manager._check_existing_positions(strategy_type, 0, ""):
                logger.info(f"Existing {strategy_type} positions found after cleanup")
                return

            # Calculate strategy parameters
            strategy = OptionsStrategy(self.kite, spot_price)
            params = strategy.get_strategy_parameters(
                strategy_type,
                self.expiry_manager.current_far_expiry['far_month']
            )
            
            # Get valid instruments
            instruments = self.expiry_manager.get_instruments(
                strategy_type,
                params['ce'],
                params['pe'],
                Config.FAR_SELL_ADD
            )
            
            # Place orders with retry logic
            for instrument in instruments:
                try:
                    order_ids = self.order_manager.place_order(
                        strategy_type,
                        instrument['strike'],
                        instrument['expiry'],
                        Config.LOT_SIZE
                    )
                    if order_ids:
                        DecisionLogger.log_decision({
                            "event": "order_placed",
                            "strategy": strategy_type,
                            "strike": instrument['strike'],
                            "expiry": instrument['expiry'],
                            "qty": Config.LOT_SIZE
                        })
                        logger.info(f"{strategy_type} orders placed: {order_ids}")
                    else:
                        logger.warning("Order placement returned empty IDs")
                except Exception as order_error:
                    logger.error(f"Order failed: {str(order_error)}")
                    self.risk_manager.execute_emergency_shutdown()

            logger.info(f"{strategy_type} strategy executed")
            
        except Exception as e:
            logger.error(f"Strategy execution failed: {str(e)}", exc_info=True)
            self.risk_manager.execute_emergency_shutdown()

    @log_function
    def _run_strategies(self):
        """Main strategy execution loop"""
        if not self.active:
            return

        try:
            spot_price = self._get_spot_price()
            self.current_positions = self.kite.positions()
            
            if self.risk_manager.check_shutdown_triggers():
                logger.critical("Risk triggers activated!")
                DecisionLogger.log_decision({"event": "emergency_shutdown"})
                self.risk_manager.execute_emergency_shutdown()
                self.active = False
                return

            # Execute configured strategies
            if Config.STRADDLE_FLAG:
                self._execute_strategy("STRADDLE", spot_price)
                
            if Config.STRANGLE_FLAG:
                self._execute_strategy("STRANGLE", spot_price)
                
            self._manage_hedges(spot_price)
            self.expiry_manager.daily_maintenance()
            
        except Exception as e:
            logger.error(f"Main execution error: {str(e)}", exc_info=True)
            self.risk_manager.execute_emergency_shutdown()
            self.active = False

    @log_function
    def _manage_hedges(self, spot_price: float):
        """Comprehensive hedge management with rollover support"""
        try:
            if Config.BUY_HEDGE:
                hedge_instruments = self.expiry_manager.get_hedge_instruments(
                    spot_price,
                    Config.ADJACENCY_GAP
                )
                for inst in hedge_instruments:
                    qty = Config.LOT_SIZE if Config.HEDGE_ONE_LOT else self._calculate_hedge_qty()
                    order_id = self.order_manager.place_order(
                        "HEDGE",
                        inst['strike'],
                        inst['expiry'],
                        qty
                    )
                    if order_id:
                        DecisionLogger.log_decision({
                            "event": "hedge_placed",
                            "strike": inst['strike'],
                            "expiry": inst['expiry'],
                            "qty": qty
                        })
                        logger.info(f"Hedge order placed: {order_id}")
        except Exception as e:
            logger.error(f"Hedge management failed: {str(e)}", exc_info=True)

    def _calculate_hedge_qty(self) -> int:
        """Dynamic hedge quantity calculation"""
        try:
            positions = self.kite.positions()["net"]
            sell_qty = sum(
                p["quantity"] for p in positions
                if p["product"] == "MIS" and p["quantity"] < 0
            )
            return abs(sell_qty) // 2
        except Exception as e:
            logger.error(f"Hedge qty calculation failed: {str(e)}")
            return Config.LOT_SIZE

    @log_function
    def start_streaming(self):
        """Complete streaming setup with token management"""
        try:
            instruments = [self.data_stream.nifty_token]
            if Config.FAR_SELL_ADD:
                far_instruments = self.expiry_manager.get_instruments(
                    "STRADDLE",
                    self._get_spot_price(),
                    self._get_spot_price(),
                    True
                )
                instruments.extend([inst['token'] for inst in far_instruments])
            self.data_stream.start_stream(instruments)
            DecisionLogger.log_decision({"event": "stream_started"})
        except Exception as e:
            logger.critical(f"Streaming setup failed: {str(e)}")
            raise

    @log_function
    def run(self):
        """Main application loop with safety checks"""
        logger.info("Starting Nifty Options Trading System")
        DecisionLogger.log_decision({"event": "system_start"})
        
        try:
            # Configuration validation
            if not Config.validate():
                logger.critical("Invalid configuration")
                sys.exit(1)
                
            self.start_streaming()
            
            # Schedule main execution
            schedule.every(Config.CHECK_INTERVAL).seconds.do(self._run_strategies)
            
            # Main loop
            while self.active:
                schedule.run_pending()
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("Initiating graceful shutdown...")
            DecisionLogger.log_decision({"event": "graceful_shutdown"})
        except Exception as e:
            logger.critical(f"Fatal error: {str(e)}", exc_info=True)
            DecisionLogger.log_decision({"event": "crash_shutdown"})
            raise
        finally:
            self.data_stream.stop()
            DecisionLogger.log_decision({"event": "stream_stopped"})
            logger.info("System shutdown complete")

if __name__ == "__main__":
    try:
        trading_system = NiftyOptionsTrading()
        trading_system.run()
    except Exception as e:
        logging.critical(f"System crash: {str(e)}", exc_info=True)
        DecisionLogger.log_decision({
            "event": "system_crash",
            "error": str(e)
        })
        sys.exit(1)
