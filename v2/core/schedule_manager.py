%%writefile /content/core/schedule_manager.py
import pytz
from datetime import datetime, time, timedelta
from dateutil import parser
from config import settings

class ScheduleManager:
    def __init__(self):
        self.config = settings.TRADE_CONFIG
        self.tz = pytz.timezone('Asia/Kolkata')
        self.trading_start = parser.parse(self.config['trading_hours']['start']).time()
        self.trading_end = parser.parse(self.config['trading_hours']['end']).time()
        
    def is_trading_time(self):
        """Check if current time is within trading hours"""
        now = datetime.now(self.tz).time()
        return self.trading_start <= now <= self.trading_end
        
    def is_trading_day(self):
        """Check if current day is valid trading day"""
        today = datetime.now(self.tz)
        date_str = today.strftime('%Y-%m-%d')
        weekday = today.strftime('%A').lower()
        
        # Check special non-weekend trading days
        if date_str in self.config['weekly_schedule']['special_weekends']:
            return True
            
        # Check holidays
        if date_str in self.config['weekly_schedule']['holidays']:
            return False
            
        # Check regular trading days
        return weekday in self.config['weekly_schedule']['days']
        
    def next_run_time(self):
        """Calculate next valid execution time"""
        now = datetime.now(self.tz)
        if not self.should_run():
            return self.next_trading_day()
            
        return now + timedelta(minutes=self.config['schedule_interval'])
        
    def next_trading_day(self):
        """Find next valid trading day"""
        day = datetime.now(self.tz) + timedelta(days=1)
        while True:
            if self._is_valid_trading_day(day):
                return day.replace(hour=9, minute=15, second=0, microsecond=0)
            day += timedelta(days=1)
            
    def _is_valid_trading_day(self, day):
        """Check if given day is valid trading day"""
        date_str = day.strftime('%Y-%m-%d')
        weekday = day.strftime('%A').lower()
        
        if date_str in self.config['weekly_schedule']['holidays']:
            return False
        if date_str in self.config['weekly_schedule']['special_weekends']:
            return True
        return weekday in self.config['weekly_schedule']['days']
        
    def sleep_duration(self):
        """Calculate seconds until next required run"""
        if self.should_run():
            next_run = self.next_run_time()
            return (next_run - datetime.now(self.tz)).total_seconds()
        return (self.next_trading_day() - datetime.now(self.tz)).total_seconds()
        
    def should_run(self):
        """Combined check for trading day/time"""
        return self.is_trading_day() and self.is_trading_time()
