# config.py
import os
from dotenv import load_dotenv
from datetime import date, timedelta

# Load environment variables
load_dotenv()

class Config:
    # --------------------------
    # Strategy Parameters
    # --------------------------
    BIAS = 0                   # Straddle ATM strike adjustment
    ADJACENCY_GAP = 100        # Minimum strike interval
    STRANGLE_GAP = 1000        # ± points from spot for strangle
    STRADDLE_FLAG = True       # Enable/disable straddle strategy
    STRANGLE_FLAG = False      # Enable/disable strangle strategy
    FAR_SELL_ADD = True        # Far-month expiry selection flag
    
    # --------------------------
    # Order Parameters
    # --------------------------
    LOT_SIZE = 50              # Contract multiplier
    HEDGE_ONE_LOT = False      # Use single lot for hedges
    BUY_HEDGE = True           # Enable loss-triggered hedging
    WS_TOKEN_LIMIT = 3000      # WebSocket subscription limit
    
    # --------------------------
    # Risk Management
    # --------------------------
    PROFIT_POINTS = 250        # Points per side for profit target
    SHUTDOWN_LOSS = 12.5       # Portfolio loss percentage threshold
    POSITION_STOPLOSS = 50     # Points loss per position trigger
    HEDGE_PREMIUM_THRESHOLD = 20  # Max premium for hedge orders
    
    # --------------------------
    # Expiry Management
    # --------------------------
    FAR_MONTH_INDEX = 3        # 0=current, 1=next, 2=far month
    ROLLOVER_DAYS_THRESHOLD = 1 # Days before expiry to roll hedges
    MARGIN_UTILIZATION_LIMIT = 75
    # --------------------------
    # Operational Config
    # --------------------------
    CHECK_INTERVAL = 300       # 5 minutes in seconds
    TRADE_DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']  # Trading schedule
    RATE_LIMIT_DELAY = 1       # Seconds between order placements
    AUTO_CLOSE_CONFLICTS = True  # Enable automatic closure of opposing positions
    POSITION_DIRECTION_CHECK = True  # Enable bidirectional position monitoring
    
    # --------------------------
    # API Credentials
    # --------------------------
    KITE_API_KEY = os.getenv("KITE_API_KEY")
    KITE_API_SECRET = os.getenv("KITE_API_SECRET")
    KITE_ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN")

    # --------------------------
    # Trading Calendar (Placeholder - Implement your own)
    # --------------------------
    class TradingCalendar:
        @staticmethod
        def is_trading_day(check_date: date) -> bool:
            """IMPLEMENT YOUR HOLIDAY CALENDAR HERE"""
            # Default implementation (Mon-Fri, no holidays)
            if check_date.weekday() > 4:  # 5=Saturday, 6=Sunday
                return False
            return True

    @staticmethod
    def validate() -> bool:
        """Configuration validation check"""
        required_vars = [
            'LOT_SIZE', 'STRADDLE_FLAG', 'STRANGLE_FLAG',
            'KITE_API_KEY', 'KITE_API_SECRET'
        ]
        return all(hasattr(Config, var) for var in required_vars)

    @staticmethod
    def get_holidays() -> list:
        """IMPLEMENT YOUR HOLIDAY DATES HERE (YYYY-MM-DD format)"""
        return [
            '2023-10-24',  # Example: Diwali
            '2023-01-26'   # Example: Republic Day
        ]

# Singleton instance
trading_calendar = Config.TradingCalendar()
