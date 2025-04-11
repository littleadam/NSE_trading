%%writefile strategies.py
import datetime
from typing import Optional, Dict, List
from config import config
from positions import PositionManager
from orders import OrderManager
from instruments import InstrumentManager
from utils import (
    is_market_open, 
    get_expiry_date, 
    filter_instruments, 
    calculate_quantity,
    round_strike,
    calculate_profit_points
)
from logger import setup_logger

log = setup_logger()

class OptionStrategy:
    def __init__(self, 
                 position_manager: Optional[PositionManager] = None,
                 order_manager: Optional[OrderManager] = None,
                 instrument_manager: Optional[InstrumentManager] = None):
        self.position_manager = position_manager or PositionManager()
        self.order_manager = order_manager or OrderManager()
        self.instrument_manager = instrument_manager or InstrumentManager()
        self.spot_price = self.instrument_manager.get_spot_price()
        log.info("Strategy initialized")

    def manage_strategy(self):
        """Main strategy execution loop"""
        log.info("Starting strategy management")
        if not is_market_open():
            log.info("Market closed - skipping
