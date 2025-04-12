# utils/helpers.py
import os
import pickle
import time
from datetime import datetime, time as dt_time
from functools import wraps
from typing import Dict, List, Optional

import pandas as pd
from kiteconnect import KiteConnect

from config import (
    ADJACENCY_GAP,
    TRADE_DAYS,
    LOT_SIZE,
    HEDGE_ONE_LOT,
    CHECK_INTERVAL
)
from utils.logger import logger

class Helpers:
    _instruments_cache = 'instruments_cache.pkl'
    _cache_expiry = 3600  # 1 hour

    @staticmethod
    def get_nearest_strike(price: float, adjacency_gap: int = ADJACENCY_GAP) -> int:
        """Round to nearest strike price based on adjacency gap"""
        return round(price / adjacency_gap) * adjacency_gap

    @staticmethod
    def fetch_instruments(kite: KiteConnect, refresh: bool = False) -> pd.DataFrame:
        """Fetch and cache instruments data with expiration"""
        try:
            if not refresh and os.path.exists(Helpers._instruments_cache):
                mtime = os.path.getmtime(Helpers._instruments_cache)
                if time.time() - mtime < Helpers._cache_expiry:
                    with open(Helpers._instruments_cache, 'rb') as f:
                        return pickle.load(f)

            logger.info("Refreshing instruments cache")
            instruments = pd.DataFrame(kite.instruments())
            with open(Helpers._instruments_cache, 'wb') as f:
                pickle.dump(instruments, f)
            return instruments
        except Exception as e:
            logger.error(f"Instrument cache error: {str(e)}")
            raise

    @staticmethod
    def calculate_quantity(hedge: bool = False) -> int:
        """Calculate order quantity based on configuration"""
        return LOT_SIZE if (HEDGE_ONE_LOT and hedge) else LOT_SIZE

    @staticmethod
    def is_market_hours() -> bool:
        """Check if current time is within trading hours"""
        now = datetime.now().time()
        return dt_time(9, 15) <= now <= dt_time(15, 30)

    @staticmethod
    def is_trading_day() -> bool:
        """Check if current day is a trading day"""
        today = datetime.now().strftime('%a')
        return today in TRADE_DAYS

    @staticmethod
    def position_synchronization(kite: KiteConnect) -> Dict:
        """Fetch and verify current positions"""
        try:
            positions = kite.positions()
            orders = kite.orders()
            
            return {
                'net_positions': positions['net'],
                'day_positions': positions['day'],
                'pending_orders': orders
            }
        except Exception as e:
            logger.error(f"Position sync failed: {str(e)}")
            raise

    @staticmethod
    def retry_api_call(max_retries: int = 3, backoff: int = 1):
        """Decorator for API call retries with exponential backoff"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                for attempt in range(max_retries):
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        if attempt == max_retries - 1:
                            raise
                        wait = backoff * (2 ** attempt)
                        logger.warning(f"Retry {attempt+1}/{max_retries} for {func.__name__} - waiting {wait}s")
                        time.sleep(wait)
                return None
            return wrapper
        return decorator

    @staticmethod
    def get_expiry_series(expiries: List[datetime], monthly_offset: int = 3) -> datetime:
        """Get far month expiry from list of expiries"""
        monthly_expiries = sorted([e for e in expiries if e.day > 25])
        if len(monthly_expiries) >= monthly_offset:
            return monthly_expiries[monthly_offset - 1]
        return monthly_expiries[-1] if monthly_expiries else None

    @staticmethod
    def validate_hedge_strikes(ce_strike: float, pe_strike: float, spot: float) -> bool:
        """Validate strangle strikes are ±1000 from spot"""
        return (ce_strike - spot >= 1000) and (spot - pe_strike >= 1000)
