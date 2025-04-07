%%writefile /content/core/safeguards.py
import logging
from datetime import datetime, time, timedelta
import pytz
from kiteconnect import KiteConnect

logger = logging.getLogger(__name__)

class Safeguards:
    def __init__(self, config):
        self.config = config
        self.tz = pytz.timezone('Asia/Kolkata')
        self.last_order_time = None
        self.order_count = 0
        self.rate_limit = 30  # Orders per minute
        self.order_history = []

    def is_market_hours(self):
        """Check if current time is within configured trading hours"""
        now = datetime.now(self.tz)
        try:
            start = datetime.strptime(self.config['trading_hours']['start'], "%H:%M").time()
            end = datetime.strptime(self.config['trading_hours']['end'], "%H:%M").time()
            return start <= now.time() <= end
        except KeyError as e:
            logger.error(f"Missing config key: {str(e)}")
            return False

    def is_trading_day(self):
        """Check if current day is valid trading day"""
        today = datetime.now(self.tz)
        date_str = today.strftime("%Y-%m-%d")
        weekday = today.strftime("%A").lower()

        # Check special weekends first
        if date_str in self.config['weekly_schedule']['special_weekends']:
            return True
            
        # Check holidays
        if date_str in self.config['weekly_schedule']['holidays']:
            return False
            
        # Check regular weekdays
        return weekday in self.config['weekly_schedule']['days']

    def check_rate_limit(self):
        """Enforce orders per minute limit"""
        now = datetime.now(self.tz)
        # Remove orders older than 1 minute
        self.order_history = [t for t in self.order_history if now - t < timedelta(minutes=1)]
        
        if len(self.order_history) >= self.rate_limit:
            logger.warning(f"Rate limit reached: {self.rate_limit} orders/min")
            time_to_wait = 60 - (now - self.order_history[0]).seconds
            logger.info(f"Waiting {time_to_wait} seconds")
            time.sleep(time_to_wait)
            return False
        return True

    def check_liquidity(self, symbol, quantity):
        """Verify sufficient market depth"""
        try:
            depth = KiteConnect().quote(symbol)['depth']
            best_5_volume = sum(item['quantity'] for item in depth['sell'][:5])
            return best_5_volume >= quantity * 3  # 3x buffer
        except Exception as e:
            logger.error(f"Liquidity check failed: {str(e)}")
            return False

    def validate_trade(self, symbol, quantity):
        """Complete pre-trade validation"""
        if not self.is_trading_day():
            logger.warning("Not a trading day")
            return False
            
        if not self.is_market_hours():
            logger.warning("Outside market hours")
            return False
            
        if not self.check_rate_limit():
            return False
            
        if not self.check_liquidity(symbol, quantity):
            logger.warning(f"Insufficient liquidity for {symbol}")
            return False
            
        return True

    def record_order(self):
        """Update order history for rate limiting"""
        self.order_history.append(datetime.now(self.tz))
