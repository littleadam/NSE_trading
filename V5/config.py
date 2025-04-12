import os
from datetime import date, timedelta
from dotenv import load_dotenv
import holidays

load_dotenv()

class TradingCalendar:
    def __init__(self):
        self.nse_holidays = self._get_nse_holidays()
        self.special_trading_days = self._get_special_trading_days()
    
    def _get_nse_holidays(self):
        """Fetch NSE holidays using python-holidays package"""
        years = [date.today().year, date.today().year + 1]
        return holidays.India(
            years=years,
            subdiv="NSE",
            observed=False
        )

    def _get_special_trading_days(self):
        """Exceptional weekends when market is open"""
        return [
            # Add specific dates from NSE circulars
            # Example: date(2023, 12, 31)
        ]

    def is_trading_day(self, dt: date) -> bool:
        if dt in self.special_trading_days:
            return True
        if dt.weekday() >= 5:  # Saturday/Sunday
            return False
        return dt not in self.nse_holidays

class Config:
    # Strategy Parameters
    STRADDLE_FLAG = os.getenv('STRADDLE_FLAG', 'False').lower() == 'true'
    STRANGLE_FLAG = os.getenv('STRANGLE_FLAG', 'False').lower() == 'true'
    BIAS = int(os.getenv('BIAS', 0))
    ADJACENCY_GAP = int(os.getenv('ADJACENCY_GAP', 100))
    PROFIT_POINTS = int(os.getenv('PROFIT_POINTS', 250))
    SHUTDOWN_LOSS = float(os.getenv('SHUTDOWN_LOSS', 12.5))
    POSITION_STOPLOSS = int(os.getenv('POSITION_STOPLOSS', 250))  # Points

    # Order Parameters
    HEDGE_ONE_LOT = os.getenv('HEDGE_ONE_LOT', 'False').lower() == 'true'
    BUY_HEDGE = os.getenv('BUY_HEDGE', 'True').lower() == 'true'
    FAR_SELL_ADD = os.getenv('FAR_SELL_ADD', 'True').lower() == 'true'

    # Operational Config
    CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', 300))
    LOT_SIZE = int(os.getenv('LOT_SIZE', 50))
    TRADING_CALENDAR = TradingCalendar()

    # Zerodha API Config
    KITE_API_KEY = os.getenv('KITE_API_KEY')
    KITE_ACCESS_TOKEN = os.getenv('KITE_ACCESS_TOKEN')
