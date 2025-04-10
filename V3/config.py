%%writefile config.py

class Config:
    def __init__(self):
        self.MARGIN_PER_LOT = 120000
        self.LOT_SIZE = 50
        # Trading Parameters
        self.POINT_VALUE = 75         # Rupees per point
        self.HEDGE_LOSS_THRESHOLD = 0.25  # 25%

        # Expiry Configuration
        self.EXPIRY_ROLLOVER_HOUR = 15  # 3 PM
        self.WEEKLY_EXPIRY_DAY = 3      # Thursday (0=Monday)
        self.MONTHLY_EXPIRY_WEEKDAY = 3 # Thursday 
        self.STRIKE_ROUNDING = 50       # Strike price rounding

        self.STRIKE_ROUNDING_INTERVAL = 50
        self.HOLIDAYS = ["2025-08-15", "2024-10-02"]
        self.ALLOW_SATURDAY = False
        self.PORTFOLIO_LOSS_THRESHOLD = 12.5
        self.ROLLOVER_TIME = "15:00"

        # Existing parameters remain same
        self.API_KEY = "your_api_key"
        self.ACCESS_TOKEN = "your_access_token"
        self.BIAS = 0
        self.ADJACENCY_GAP = 50
        self.PROFIT_POINTS = 250
        self.SHUTDOWN_LOSS = 0.125
        self.STRADDLE_FLAG = True
        self.STRANGLE_FLAG = False
        self.FAR_SELL_ADD = True
        self.BUY_HEDGE = True
        self.CHECK_INTERVAL = 300
        self.TRADING_HOURS = {"start": "09:15", "end": "15:30"}
        self.EXPIRY_MONTHS = 3
        self.STRANGLE_DISTANCE = 1000
        self.PROFIT_THRESHOLD = 0.25
        self.STOPLOSS_THRESHOLD = 0.90

config = Config()
