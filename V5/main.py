# main.py
import os
import time
import schedule
import logging
from datetime import datetime, time as dt_time
from typing import Dict, Optional

from config import (
    BIAS,
    ADJACENCY_GAP,
    PROFIT_POINTS,
    SHUTDOWN_LOSS,
    HEDGE_ONE_LOT,
    BUY_HEDGE,
    FAR_SELL_ADD,
    CHECK_INTERVAL,
    TRADE_DAYS,
    LOT_SIZE
)
from auth.kite_auth import KiteAuth
from core.strategy import NiftyStrategy
from core.order_manager import OrderManager
from core.risk_manager import RiskManager
from core.expiry_manager import ExpiryManager
from core.streaming import DataStream
from utils.logger import setup_logger
from utils.helpers import is_holiday

class NiftyOptionsTrading:
    def __init__(self):
        setup_logger()
        self.logger = logging.getLogger(__name__)
        self.kite = self._initialize_kite()
        self.order_manager = OrderManager(self.kite)
        self.risk_manager = RiskManager(self.kite)
        self.expiry_manager = ExpiryManager(self.kite)
        self.data_stream: Optional[DataStream] = None
        self.current_positions: Dict = {}

    def _initialize_kite(self):
        try:
            auth = KiteAuth()
            return auth.get_kite()
        except Exception as e:
            self.logger.error(f"Authentication failed: {str(e)}")
            raise

    def _market_time_check(self) -> bool:
        now = datetime.now()
        if now.strftime("%a") not in TRADE_DAYS:
            self.logger.info("Non-trading day")
            return False
            
        if is_holiday(now.date()):
            self.logger.info("Market holiday")
            return False
            
        current_time = now.time()
        if not (dt_time(9, 15) <= current_time <= dt_time(15, 30)):
            self.logger.info("Outside market hours")
            return False
            
        return True

    def _get_spot_price(self) -> float:
        try:
            nifty_quote = self.kite.quote("NSE:NIFTY 50")
            return nifty_quote["last_price"]
        except Exception as e:
            self.logger.error(f"Spot price fetch failed: {str(e)}")
            raise

    def _execute_strategy(self, strategy_type: str, spot_price: float):
        try:
            if self.order_manager.check_existing_positions(strategy_type):
                self.logger.info(f"Existing {strategy_type} positions found")
                return

            strategy = NiftyStrategy(self.kite, spot_price)
            strikes = strategy.calculate_strikes(strategy_type)
            
            if strategy_type == "STRADDLE":
                ce_strike = strikes
                pe_strike = ce_strike + BIAS
            else:  # Strangle
                ce_strike = strikes["ce"]
                pe_strike = strikes["pe"]

            instruments = self.expiry_manager.get_instruments(
                strategy_type,
                ce_strike,
                pe_strike,
                FAR_SELL_ADD
            )
            
            for instrument in instruments:
                self.order_manager.place_order(
                    instrument["tradingsymbol"],
                    LOT_SIZE * instrument["lot_size"],
                    "SELL"
                )

            self.logger.info(f"{strategy_type} strategy executed")
            
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

            if os.getenv("STRADDLE_FLAG", "False").lower() == "true":
                self._execute_strategy("STRADDLE", spot_price)
                
            if os.getenv("STRANGLE_FLAG", "False").lower() == "true":
                self._execute_strategy("STRANGLE", spot_price)
                
            self._manage_hedges(spot_price)
            
        except Exception as e:
            self.logger.error(f"Main execution error: {str(e)}")

    def _manage_hedges(self, spot_price: float):
        try:
            if BUY_HEDGE:
                hedge_instruments = self.expiry_manager.get_hedge_instruments(
                    spot_price,
                    ADJACENCY_GAP
                )
                for inst in hedge_instruments:
                    qty = LOT_SIZE if HEDGE_ONE_LOT else self._calculate_hedge_qty()
                    self.order_manager.place_order(
                        inst["tradingsymbol"],
                        qty,
                        "BUY"
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
            return LOT_SIZE

    def start_streaming(self):
        instruments = [
            "NSE:NIFTY 50",
            "NFO:NIFTY23...",  # Add actual instrument tokens
        ]
        self.data_stream = DataStream(
            api_key=os.getenv("KITE_API_KEY"),
            access_token=self.kite.access_token
        )
        self.data_stream.start_stream(instruments)

    def run(self):
        self.logger.info("Starting Nifty Options Trading System")
        self.start_streaming()
        
        schedule.every(CHECK_INTERVAL).seconds.do(self._run_strategies)
        
        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Shutting down gracefully...")
        finally:
            if self.data_stream:
                self.data_stream.disconnect()

if __name__ == "__main__":
    try:
        trading_system = NiftyOptionsTrading()
        trading_system.run()
    except Exception as e:
        logging.critical(f"System crash: {str(e)}")
        raise
