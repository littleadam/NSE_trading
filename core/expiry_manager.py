import os
import logging
import datetime
import pandas as pd
from kiteconnect import KiteConnect

class ExpiryManager:
    def __init__(self, kite, logger, config):
        """
        Initialize ExpiryManager with KiteConnect instance
        
        Args:
            kite: Authenticated KiteConnect instance
            logger: Logger instance
            config: Configuration instance
        """
        self.kite = kite
        self.logger = logger
        self.config = config
        self.logger.info("ExpiryManager: Initializing expiry manager")
        
        # Cache for expiry dates
        self.monthly_expiry_dates = []
        self.weekly_expiry_dates = []
        
        # Initialize cache
        self._init_expiry_dates()
        self.logger.info("ExpiryManager: Expiry manager initialized")
    
    def _init_expiry_dates(self):
        """
        Initialize expiry dates cache
        """
        try:
            self.logger.info("ExpiryManager: Initializing expiry dates cache")
            all_instruments = self.kite.instruments("NFO")
            
            # Filter for NIFTY options
            nifty_options = [i for i in all_instruments if i['name'] == 'NIFTY']
            
            # Extract unique expiry dates
            all_expiry_dates = sorted(list(set([i['expiry'] for i in nifty_options])))
            
            # Separate monthly and weekly expiries
            # Monthly expiries are typically the last Thursday of each month
            monthly_expiries = []
            weekly_expiries = []
            
            # Group expiries by month
            expiry_by_month = {}
            for expiry in all_expiry_dates:
                month_key = expiry.strftime('%Y-%m')
                if month_key not in expiry_by_month:
                    expiry_by_month[month_key] = []
                expiry_by_month[month_key].append(expiry)
            
            # Last expiry of each month is the monthly expiry
            for month, expiries in expiry_by_month.items():
                monthly_expiries.append(max(expiries))
                # All other expiries in the month are weekly
                weekly_expiries.extend([e for e in expiries if e != max(expiries)])
            
            self.monthly_expiry_dates = sorted(monthly_expiries)
            self.weekly_expiry_dates = sorted(weekly_expiries)
            
            self.logger.info(f"ExpiryManager: Cached {len(self.monthly_expiry_dates)} monthly and {len(self.weekly_expiry_dates)} weekly expiry dates")
        except Exception as e:
            self.logger.error(f"ExpiryManager: Failed to initialize expiry dates cache: {str(e)}")
            raise
    
    def get_far_month_expiry(self):
        """
        Get the expiry date that is 3 monthly expiries away
        
        Returns:
            Expiry date (datetime.date) or None if not available
        """
        today = datetime.datetime.now().date()
        
        # Ensure we have enough expiry dates cached
        if len(self.monthly_expiry_dates) < self.config.far_month_expiry:
            self.logger.warning("ExpiryManager: Not enough monthly expiry dates cached")
            self._init_expiry_dates()
            
            if len(self.monthly_expiry_dates) < self.config.far_month_expiry:
                self.logger.error("ExpiryManager: Still not enough monthly expiry dates after refresh")
                return None
        
        # Filter future expiries
        future_expiries = [exp for exp in self.monthly_expiry_dates if exp.date() > today]
        
        if len(future_expiries) < self.config.far_month_expiry:
            self.logger.warning("ExpiryManager: Less than 3 future monthly expiries available")
            return future_expiries[-1] if future_expiries else None
        
        # Return the 3rd future monthly expiry
        return future_expiries[2]
    
    def get_next_weekly_expiry(self):
        """
        Get the next weekly expiry date
        
        Returns:
            Expiry date (datetime.date) or None if not available
        """
        today = datetime.datetime.now().date()
        
        # Filter future weekly expiries
        future_weekly_expiries = [exp for exp in self.weekly_expiry_dates if exp.date() > today]
        
        if not future_weekly_expiries:
            # If no future weekly expiries, check monthly expiries
            future_monthly_expiries = [exp for exp in self.monthly_expiry_dates if exp.date() > today]
            return future_monthly_expiries[0] if future_monthly_expiries else None
        
        # Return the next weekly expiry
        return future_weekly_expiries[0]
    
    def is_expiry_day(self, expiry_date=None):
        """
        Check if today is an expiry day
        
        Args:
            expiry_date: Specific expiry date to check (optional)
            
        Returns:
            True if today is an expiry day, False otherwise
        """
        today = datetime.datetime.now().date()
        
        if expiry_date:
            if isinstance(expiry_date, datetime.datetime):
                expiry_date = expiry_date.date()
            return today == expiry_date
        
        # Check if today is in any expiry date
        all_expiries = [exp.date() for exp in self.monthly_expiry_dates + self.weekly_expiry_dates]
        return today in all_expiries
    
    def get_days_to_expiry(self, expiry_date):
        """
        Get the number of days to expiry
        
        Args:
            expiry_date: Expiry date
            
        Returns:
            Number of days to expiry
        """
        if isinstance(expiry_date, datetime.datetime):
            expiry_date = expiry_date.date()
        
        today = datetime.datetime.now().date()
        return (expiry_date - today).days
    
    def is_monthly_expiry(self, expiry_date):
        """
        Check if the given expiry date is a monthly expiry
        
        Args:
            expiry_date: Expiry date to check
            
        Returns:
            True if it's a monthly expiry, False otherwise
        """
        if isinstance(expiry_date, datetime.date):
            expiry_date = datetime.datetime.combine(expiry_date, datetime.time())
        
        return expiry_date in self.monthly_expiry_dates
    
    def get_expiry_type(self, expiry_date):
        """
        Get the type of expiry (monthly or weekly)
        
        Args:
            expiry_date: Expiry date to check
            
        Returns:
            'monthly' or 'weekly'
        """
        if self.is_monthly_expiry(expiry_date):
            return 'monthly'
        return 'weekly'
    
    def get_all_expiries(self):
        """
        Get all expiry dates (both monthly and weekly)
        
        Returns:
            List of all expiry dates
        """
        return sorted(self.monthly_expiry_dates + self.weekly_expiry_dates)
    
    def get_monthly_expiries(self):
        """
        Get all monthly expiry dates
        
        Returns:
            List of monthly expiry dates
        """
        return self.monthly_expiry_dates.copy()
    
    def get_weekly_expiries(self):
        """
        Get all weekly expiry dates
        
        Returns:
            List of weekly expiry dates
        """
        return self.weekly_expiry_dates.copy()
    
    def refresh_expiry_dates(self):
        """
        Refresh expiry dates cache
        """
        self.logger.info("ExpiryManager: Refreshing expiry dates cache")
        self._init_expiry_dates()
