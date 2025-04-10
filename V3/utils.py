%%writefile utils.py
import datetime
import logging
import math
from dateutil.relativedelta import relativedelta
from kiteconnect import KiteConnect
from config import *
import pandas as pd


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
        # Use pandas to get the last business day of the month
        return pd.date_range(current_date, periods=1, freq='BME')[0].date()
    elif expiry_type == 'weekly':
        # Offset to next weekly expiry day
        days_to_expiry = (WEEKLY_EXPIRY_DAY - current_date.weekday()) % 7
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
