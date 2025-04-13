# config.py
import os
from datetime import date, timedelta
from dotenv import load_dotenv
import holidays

load_dotenv()

class TradingCalendar:
    def __init__(self):
        self.nse_holidays = self._get_nse_holidays()
        self.special_trading_days = self._get_special_trading_days()
    
    def _get_nse_holidays(self) -> set:
        """Fetch NSE holidays using python-holidays package"""
        years = [date.today().year, date.today().year + 1]
        return holidays.India(
            years=years,
            subdiv="NSE",
            observed=False
        )

    def _get_special_trading_days(self) -> list:
        """Exceptional weekends when market is open"""
        return [
            # Add specific dates from NSE circulars as datetime.date objects
            # Example: date(2023, 12, 31)
        ]

    def is_trading_day(self, dt: date) -> bool:
        """Check if date is valid trading day"""
        if dt in self.special_trading_days:
            return True
        if dt.weekday() >= 5:  # Saturday/Sunday
            return False
        return dt not in self.nse_holidays

class Config:
    # --------------------------
    # Strategy Parameters
    # --------------------------
    STRADDLE_FLAG = os.getenv('STRADDLE_FLAG', 'False').lower() == 'true'
    STRANGLE_FLAG = os.getenv('STRANGLE_FLAG', 'False').lower() == 'true'
    BIAS = int(os.getenv('BIAS', 0))  # Straddle strike adjustment
    ADJACENCY_GAP = int(os.getenv('ADJACENCY_GAP', 100))  # Hedge adjustment interval
    PROFIT_POINTS = int(os.getenv('PROFIT_POINTS', 250))  # Profit-taking threshold
    SHUTDOWN_LOSS = float(os.getenv('SHUTDOWN_LOSS', 12.5))  # Portfolio loss percentage
    HEDGE_PREMIUM_THRESHOLD = float(os.getenv('HEDGE_PREMIUM_THRESHOLD', 50.0))
    POSITION_STOPLOSS = int(os.getenv('POSITION_STOPLOSS', 250))  # Points
    
    # --------------------------
    # Order Parameters
    # --------------------------
    HEDGE_ONE_LOT = os.getenv('HEDGE_ONE_LOT', 'False').lower() == 'true'
    BUY_HEDGE = os.getenv('BUY_HEDGE', 'True').lower() == 'true'
    FAR_SELL_ADD = os.getenv('FAR_SELL_ADD', 'True').lower() == 'true'
    
    # --------------------------
    # Operational Config
    # --------------------------
    CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', 300))  # 5 minutes
    LOT_SIZE = int(os.getenv('LOT_SIZE', 50))  # Contract multiplier
    TRADE_DAYS = os.getenv('TRADE_DAYS', 'Mon,Tue,Wed,Thu,Fri').split(',')
    TRADING_CALENDAR = TradingCalendar()
    
    # --------------------------
    # Zerodha API Config
    # --------------------------
    KITE_API_KEY = os.getenv('KITE_API_KEY')
    KITE_ACCESS_TOKEN = os.getenv('KITE_ACCESS_TOKEN')
    KITE_API_SECRET = os.getenv('KITE_API_SECRET')
    
    # --------------------------
    # Risk Management
    # --------------------------
    MAX_RETRIES = int(os.getenv('MAX_RETRIES', 3))
    ORDER_RETRY_DELAY = int(os.getenv('ORDER_RETRY_DELAY', 2))
    TOKEN_LIMIT = int(os.getenv('TOKEN_LIMIT', 3000))  # Zerodha WS limit
    
    # --------------------------
    # Logging Configuration
    # --------------------------
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FORMAT = '%(asctime)s | %(name)s | %(funcName)s:%(lineno)d | %(levelname)s | %(message)s'
    LOG_FILE = os.getenv('LOG_FILE', 'trading_app.log')
    LOG_ROTATION_SIZE = int(os.getenv('LOG_ROTATION_SIZE', 10))  # MB
    LOG_BACKUP_COUNT = int(os.getenv('LOG_BACKUP_COUNT', 5))
