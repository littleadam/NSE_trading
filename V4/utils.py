%%writefile utils.py
import datetime
import logging
import math
import pandas as pd
import pandas_market_calendars as mcal
from dateutil.relativedelta import relativedelta
from typing import List, Dict, Optional
from config import config
from logger import setup_logger

log = setup_logger()

def is_trading_day(date: datetime.date) -> bool:
    """Check if the date is a valid trading day"""
    log.debug(f"Checking trading day for {date}")
    try:
        nse = mcal.get_calendar('NSE')
        schedule = nse.schedule(start_date=date, end_date=date)
        result = not schedule.empty
        log.debug(f"is_trading_day result: {result}")
        return result
    except Exception as e:
        log.error("Failed to check trading day", exc_info=True)
        return False

def round_strike(strike: float) -> int:
    """Round strike price to nearest configured interval"""
    log.debug(f"Rounding strike {strike}")
    result = round(strike / config.STRIKE_ROUNDING) * config.STRIKE_ROUNDING
    log.debug(f"Rounded strike: {result}")
    return result

def is_market_open() -> bool:
    """Check if market is currently open"""
    log.debug("Checking market status")
    try:
        nse = mcal.get_calendar('NSE')
        now = datetime.datetime.now(datetime.timezone.utc)
        schedule = nse.schedule(start_date=now.date(), end_date=now.date())
        
        if schedule.empty:
            log.debug("Market closed: No trading scheduled")
            return False
            
        market_open = schedule.iloc[0].market_open
        market_close = schedule.iloc[0].market_close
        result = market_open <= now <= market_close
        log.debug(f"Market open status: {result}")
        return result
    except Exception as e:
        log.error("Market check failed", exc_info=True)
        return False

def get_expiry_date(expiry_type: str, current_date: datetime.date = None) -> datetime.date:
    """Calculate expiry date for given type"""
    current_date = current_date or datetime.date.today()
    log.debug(f"Calculating {expiry_type} expiry from {current_date}")
    try:
        if expiry_type == 'monthly':
            month = current_date.month + config.EXPIRY_MONTHS
            year = current_date.year + (month - 1) // 12
            month = (month - 1) % 12 + 1
            next_month = datetime.date(year, month, 1)
            result = next_month + relativedelta(day=31, weekday=relativedelta.TH(-1))
        elif expiry_type == 'weekly':
            days_to_thursday = (3 - current_date.weekday()) % 7
            expiry = current_date + datetime.timedelta(days=days_to_thursday)
            result = expiry if expiry > current_date else expiry + datetime.timedelta(weeks=1)
        else:
            raise ValueError(f"Invalid expiry type: {expiry_type}")
        
        log.debug(f"Expiry date calculated: {result}")
        return result
    except Exception as e:
        log.error("Expiry calculation failed", exc_info=True)
        raise

def calculate_quantity(margin_available: float, volatility: float = 0) -> int:
    """Calculate order quantity with volatility placeholder"""
    log.debug(f"Calculating quantity: Margin={margin_available}, Vol={volatility}")
    try:
        max_lots = max(1, int(margin_available // config.MARGIN_PER_LOT))
        result = max_lots * config.LOT_SIZE
        log.debug(f"Calculated quantity: {result}")
        return result
    except Exception as e:
        log.error("Quantity calculation failed", exc_info=True)
        return 0

def filter_instruments(instruments: List[Dict], expiry_date: datetime.date, 
                      option_type: str, strike: Optional[float] = None) -> List[Dict]:
    """Filter instruments by parameters"""
    log.debug(f"Filtering instruments: {expiry_date}, {option_type}, {strike}")
    try:
        target_strike = round_strike(strike) if strike else None
        filtered = [
            inst for inst in instruments
            if inst['expiry'] == expiry_date
            and inst['instrument_type'] == option_type
            and (target_strike is None or inst['strike'] == target_strike)
        ]
        result = sorted(filtered, key=lambda x: x['strike'])
        log.debug(f"Found {len(result)} matching instruments")
        return result
    except Exception as e:
        log.error("Instrument filtering failed", exc_info=True)
        raise

def calculate_profit_points(points: int) -> float:
    """Convert points to monetary value"""
    log.debug(f"Calculating profit points: {points}")
    result = points * config.POINT_VALUE
    log.debug(f"Profit value: {result}")
    return result
