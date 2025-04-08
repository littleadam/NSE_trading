%%writefile utils.py
import datetime
import logging
import math
from dateutil.relativedelta import relativedelta
from kiteconnect import KiteConnect

logging.basicConfig(level=logging.INFO)

def is_market_open():
    now = datetime.datetime.now().time()
    start = datetime.time(9, 15)
    end = datetime.time(15, 30)
    return start <= now <= end

def get_expiry_date(expiry_type, current_date=None):
    current_date = current_date or datetime.date.today()
    if expiry_type == 'monthly':
        # Get last Thursday of the month
        next_month = current_date + relativedelta(months=1)
        last_day = next_month.replace(day=31)
        offset = (last_day.weekday() - 3) % 7
        expiry = last_day - datetime.timedelta(days=offset)
        return expiry
    elif expiry_type == 'weekly':
        # Get next Thursday
        days_to_thursday = (3 - current_date.weekday()) % 7
        if days_to_thursday == 0:  # Today is Thursday
            if datetime.datetime.now().hour >= 15:  # After market close
                days_to_thursday = 7
        return current_date + datetime.timedelta(days=days_to_thursday)

def calculate_quantity(margin_available, volatility):
    # Simplified margin calculation (NIFTY margin ~1.2L per lot)
    margin_per_lot = 120000
    max_lots = math.floor(margin_available / margin_per_lot)
    return max_lots * 50  # 50 shares per lot

def filter_instruments(instruments, expiry_date, option_type, strike=None):
    filtered = []
    for inst in instruments.values():
        if inst['instrument_type'] != 'CE' and inst['instrument_type'] != 'PE':
            continue
        if inst['expiry'] != expiry_date:
            continue
        if strike is not None and inst['strike'] != strike:
            continue
        if inst['instrument_type'] == option_type:
            filtered.append(inst)
    return sorted(filtered, key=lambda x: x['strike'])
