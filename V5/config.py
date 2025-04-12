# config.py
import os
from datetime import datetime
from dotenv import load_dotenv
import holidays

load_dotenv('./auth/.env')

# API Configuration
API_KEY = os.getenv('KITE_API_KEY')
ACCESS_TOKEN = os.getenv('KITE_ACCESS_TOKEN')

# Strategy Configuration
STRADDLE_FLAG = os.getenv('STRADDLE_FLAG', 'False').lower() == 'true'
STRANGLE_FLAG = os.getenv('STRANGLE_FLAG', 'False').lower() == 'true'
BIAS = int(os.getenv('BIAS', 0))
ADJACENCY_GAP = int(os.getenv('ADJACENCY_GAP', 100))
PROFIT_POINTS = int(os.getenv('PROFIT_POINTS', 250))
SHUTDOWN_LOSS = float(os.getenv('SHUTDOWN_LOSS', 12.5))

# Order Configuration
HEDGE_ONE_LOT = os.getenv('HEDGE_ONE_LOT', 'False').lower() == 'true'
BUY_HEDGE = os.getenv('BUY_HEDGE', 'True').lower() == 'true'
FAR_SELL_ADD = os.getenv('FAR_SELL_ADD', 'True').lower() == 'true'
LOT_SIZE = int(os.getenv('LOT_SIZE', 50))

# Schedule Configuration
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', 300))  # 5 minutes in seconds
TRADING_WINDOW = ('09:15', '15:30')

# Holiday Configuration (2023-2024 NSE Holidays)
NSE_HOLIDAYS = holidays.India(
    years=[2025, 2026],
    subdiv='NSE',
    observed=True
)

# Special Trading Days (Sat/Sun when market opens)
SPECIAL_TRADING_DAYS = [
    datetime(2023, 1, 14).date(),  # Example special trading session
    datetime(2023, 3, 5).date()
]

# Expiry Configuration
FAR_EXPIRY_MONTHS = 3  # Monthly expiries away from current
