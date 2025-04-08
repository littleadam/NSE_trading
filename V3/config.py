%%writefile config.py
# Trading Parameters
MARGIN_PER_LOT = 120000  # Margin required per lot
LOT_SIZE = 50            # Shares per lot
POINT_VALUE = 75         # Rupees per point
HEDGE_LOSS_THRESHOLD = 0.25  # 25%

# Expiry Configuration
EXPIRY_ROLLOVER_HOUR = 15  # 3 PM
WEEKLY_EXPIRY_DAY = 3      # Thursday (0=Monday)
MONTHLY_EXPIRY_WEEKDAY = 3 # Thursday 
STRIKE_ROUNDING = 50       # Strike price rounding

# Existing parameters remain same
API_KEY = "your_api_key"
ACCESS_TOKEN = "your_access_token"
BIAS = 0
ADJACENCY_GAP = 50
PROFIT_POINTS = 250
SHUTDOWN_LOSS = 0.125
STRADDLE_FLAG = True
STRANGLE_FLAG = False
FAR_SELL_ADD = True
BUY_HEDGE = True
CHECK_INTERVAL = 300
TRADING_HOURS = {"start": "09:15", "end": "15:30"}
EXPIRY_MONTHS = 3
STRANGLE_DISTANCE = 1000
PROFIT_THRESHOLD = 0.25
STOPLOSS_THRESHOLD = 0.90
