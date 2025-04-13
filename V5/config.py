# config.py
from datetime import datetime, date
from typing import List

class Config:
    """Central configuration for trading system parameters"""
    
    # --------------------------
    # Strategy Parameters
    # --------------------------
    BIAS = 0                   # Straddle ATM strike adjustment
    ADJACENCY_GAP = 100        # Minimum strike interval
    PROFIT_POINTS = 250        # Points per lot for profit target
    SHUTDOWN_LOSS = 12.5       # Portfolio loss percentage (0-100)
    STRANGLE_GAP = 1000        # Points from spot for strangle strikes
    POSITION_STOPLOSS = 250    # Points loss per position for SL
    
    # --------------------------
    # Order Parameters
    # --------------------------
    HEDGE_ONE_LOT = False      # Use single lot for hedges
    BUY_HEDGE = True           # Enable loss-triggered hedging
    FAR_SELL_ADD = True        # Use far expiry for profit adjustments
    HEDGE_PREMIUM_THRESHOLD = 30.0  # Max premium for hedge orders
    
    # --------------------------
    # Expiry Management
    # --------------------------
    ROLLOVER_DAYS_THRESHOLD = 2     # Days remaining for hedge rollover
    FAR_MONTH_INDEX = 2             # 0-based index for 3rd monthly expiry
    
    # --------------------------
    # Operational Config
    # --------------------------
    LOT_SIZE = 50              # Contract multiplier
    CHECK_INTERVAL = 300       # Strategy check interval in seconds (5 mins)
    STRIKE_ADJUSTMENT_FACTOR = 1.10  # Stop-loss price multiplier
    
    # --------------------------
    # API & Streaming
    # --------------------------
    API_MAX_RETRIES = 3        # Max retries for API calls
    API_BACKOFF_FACTOR = 1     # Exponential backoff base
    STREAMING_MAX_RETRIES = 3  # Websocket connection retries
    STREAMING_TOKEN_LIMIT = 3000  # Zerodha WS token limit
    
    # --------------------------
    # Trading Schedule
    # --------------------------
    TRADE_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]  # Valid trading days
    MARKET_OPEN_TIME = (9, 15)  # 09:15 hrs
    MARKET_CLOSE_TIME = (15, 30) # 15:30 hrs

    # --------------------------
    # Trading Calendar
    # --------------------------
    class TRADING_CALENDAR:
        # Static list of market holidays (YYYY-MM-DD)
        HOLIDAYS = [
            "2024-01-26",  # Republic Day
            "2024-03-08",  # Maha Shivaratri
            "2024-03-25",  # Holi
            "2024-04-11",  # Idul Fitr
            "2024-05-01",  # Labour Day
        ]

        @classmethod
        def is_trading_day(cls, dt: date) -> bool:
            """Check if date is valid trading day"""
            # Weekend check
            if dt.weekday() >= 5:  # 5=Saturday, 6=Sunday
                return False
            
            # Date string comparison
            date_str = dt.strftime("%Y-%m-%d")
            if date_str in cls.HOLIDAYS:
                return False
                
            # Add special day logic here
            return True

        @classmethod
        def is_market_hours(cls) -> bool:
            """Check if current time is within trading hours"""
            now = datetime.now().time()
            open_time = dt_time(*cls.MARKET_OPEN_TIME)
            close_time = dt_time(*cls.MARKET_CLOSE_TIME)
            return open_time <= now <= close_time

    # --------------------------
    # Derived Parameters
    # --------------------------
    @property
    def PROFIT_THRESHOLD(self):
        """Calculated profit target per strategy"""
        return self.PROFIT_POINTS * self.LOT_SIZE

    @property
    def MIN_STRIKE_DISTANCE(self):
        """Minimum allowed strike distance from spot"""
        return self.ADJACENCY_GAP * 2
