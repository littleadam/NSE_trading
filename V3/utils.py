%%writefile utils.py
import datetime
import logging
import math
from dateutil.relativedelta import relativedelta
from kiteconnect import KiteConnect
from config import *

logging.basicConfig(level=logging.INFO)

def round_strike(strike):
    return round(strike / STRIKE_ROUNDING_INTERVAL) * STRIKE_ROUNDING_INTERVAL

def is_market_open():
    now = datetime.datetime.now().time()
    start = datetime.datetime.strptime(TRADING_HOURS['start'], "%H:%M").time()
    end = datetime.datetime.strptime(TRADING_HOURS['end'], "%H:%M").time()
    return start <= now <= end

def get_expiry_date(expiry_type, current_date=None):
    current_date = current_date or datetime.date.today()
    if expiry_type == 'monthly':
        # Get nth weekday of the month
        month = current_date.month + EXPIRY_MONTHS
        year = current_date.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        day = 1
        last_day = datetime.date(year, month, day) + relativedelta(day=31)
        
        # Find specific weekday
        offset = (last_day.weekday() - MONTHLY_EXPIRY_WEEKDAY) % 7
        expiry = last_day - datetime.timedelta(days=offset)
        
        # Check rollover time
        if datetime.datetime.now().hour >= EXPIRY_ROLLOVER_HOUR:
            expiry = expiry + relativedelta(months=1)
            offset = (expiry.weekday() - MONTHLY_EXPIRY_WEEKDAY) % 7
            expiry = expiry - datetime.timedelta(days=offset)
        
        return expiry
    elif expiry_type == 'weekly':
        days_to_expiry = (WEEKLY_EXPIRY_DAY - current_date.weekday()) % 7
        if days_to_expiry == 0:  # Today is expiry day
            if datetime.datetime.now().hour >= EXPIRY_ROLLOVER_HOUR:
                days_to_expiry = 7
        return current_date + datetime.timedelta(days=days_to_expiry)

def calculate_quantity(margin_available, volatility):
    max_lots = math.floor(margin_available / MARGIN_PER_LOT)
    return max_lots * LOT_SIZE

def filter_instruments(instruments, expiry_date, option_type, strike=None):
    filtered = []
    for inst in instruments.values():
        if inst['instrument_type'] != option_type:
            continue
        if inst['expiry'] != expiry_date:
            continue
        if strike is not None:
            rounded_strike = round(strike/STRIKE_ROUNDING)*STRIKE_ROUNDING
            if inst['strike'] != rounded_strike:
                continue
        filtered.append(inst)
    return sorted(filtered, key=lambda x: x['strike'])

def calculate_profit_points(points):
    return points * POINT_VALUE
