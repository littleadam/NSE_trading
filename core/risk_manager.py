import os
import logging
import datetime
import pandas as pd
from kiteconnect import KiteConnect

class RiskManager:
    def __init__(self, kite, logger, config, order_manager):
        """
        Initialize RiskManager with KiteConnect instance
        
        Args:
            kite: Authenticated KiteConnect instance
            logger: Logger instance
            config: Configuration instance
            order_manager: OrderManager instance
        """
        self.kite = kite
        self.logger = logger
        self.config = config
        self.order_manager = order_manager
        self.logger.info("RiskManager: Initializing risk manager")
        
        # Portfolio metrics
        self.capital_allocated = self.config.capital_allocated
        self.shutdown_loss_percentage = self.config.shutdown_loss
        self.shutdown_loss_amount = self.capital_allocated * (self.shutdown_loss_percentage / 100)
        
        self.logger.info(f"RiskManager: Shutdown loss set at {self.shutdown_loss_percentage}% (₹{self.shutdown_loss_amount:.2f})")
        self.logger.info("RiskManager: Risk manager initialized")
    
    def get_monthly_pnl(self):
         """
         Get PnL for the current month
         
         Returns:
             Dictionary with realized and unrealized PnL
         """
         try:
             # Get current month start date
             today = datetime.datetime.now()
             month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
             
             # Get positions
             positions = self.order_manager.refresh_positions()
             
             # Calculate unrealized PnL
             unrealized_pnl = 0
             for position in positions.get('net', []):
                 unrealized_pnl += position.get('unrealised_pnl', 0)
             
             # Calculate realized PnL
             realized_pnl = 0
             for position in positions.get('net', []):
                 realized_pnl += position.get('realised_pnl', 0)
             
             # Get completed trades for the month
             orders = self.order_manager.refresh_orders()
             monthly_orders = []
             for order in orders:
                 if 'order_timestamp' in order:
                     order_time = pd.to_datetime(order['order_timestamp'])
                     if order_time >= month_start and order['status'] == 'COMPLETE':
                         monthly_orders.append(order)
             
             return {
                 'unrealized_pnl': unrealized_pnl,
                 'realized_pnl': realized_pnl,
                 'total_pnl': unrealized_pnl + realized_pnl,
                 'monthly_orders': monthly_orders
             }
         except Exception as e:
             self.logger.error(f"RiskManager: Error calculating monthly PnL: {str(e)}")
             return {
                 'unrealized_pnl': 0,
                 'realized_pnl': 0,
                 'total_pnl': 0,
                 'monthly_orders': []
             }
             
    def check_shutdown_condition(self):
        """
        Check if the shutdown condition is met (unrealized loss exceeds threshold)
        
        Returns:
            True if shutdown condition is met, False otherwise
        """
        try:
            self.logger.info("RiskManager: Checking shutdown condition")
            
            # Get monthly PnL
            monthly_pnl = self.get_monthly_pnl()
            total_pnl = monthly_pnl['total_pnl']
            
            self.logger.info(f"RiskManager: Current unrealized PnL: ₹{total_pnl:.2f}")
            
            # Calculate shutdown threshold
            shutdown_threshold = -(self.config.capital_allocated * self.config.shutdown_loss / 100)

            self.logger.info(f"RiskManager: Checking shutdown condition - Monthly PnL: {total_pnl}, Threshold: {shutdown_threshold}")

            # Check if monthly PnL exceeds shutdown threshold
            if total_pnl <= shutdown_threshold:
                self.logger.warning(f"RiskManager: Shutdown condition met - Monthly PnL ({total_pnl}) exceeds threshold ({shutdown_threshold})")
                return True
                
            self.logger.info("RiskManager: Shutdown condition not met")
            return False
        except Exception as e:
            self.logger.error(f"RiskManager: Error checking shutdown condition: {str(e)}")
            # In case of error, don't trigger shutdown
            return False
    
    def check_profit_exit_condition(self, instrument_token, option_type):
        """
        Check if profit exit condition is met for a specific option type (CE or PE)
        
        Args:
            instrument_token: Instrument token
            option_type: Option type (CE or PE)
            
        Returns:
            True if profit exit condition is met, False otherwise
        """
        try:
            self.logger.info(f"RiskManager: Checking profit exit condition for {option_type}")
            
            # Refresh positions
            positions = self.order_manager.refresh_positions()
            if not positions:
                self.logger.warning("RiskManager: Could not refresh positions, skipping profit exit check")
                return False
            
            # Filter positions by option type
            option_positions = []
            for position in positions.get('net', []):
                # Check if this position is for the specified option type
                if position['tradingsymbol'].endswith(option_type):
                    option_positions.append(position)
            
            if not option_positions:
                self.logger.info(f"RiskManager: No {option_type} positions found")
                return False
            
            # Calculate total profit in points
            total_profit_points = 0
            for position in option_positions:
                # For short positions, profit is positive when price goes down
                if position['quantity'] < 0:  # Short position
                    entry_price = position['sell_price']
                    current_price = self.order_manager.get_ltp(position['instrument_token'])
                    if current_price and entry_price:
                        profit_points = (entry_price - current_price) * abs(position['quantity'])
                        total_profit_points += profit_points
            
            self.logger.info(f"RiskManager: Total profit for {option_type} positions: {total_profit_points:.2f} points")
            
            # Check if profit exceeds threshold
            if total_profit_points >= self.config.profit_points:
                self.logger.info(f"RiskManager: Profit exit condition met for {option_type}! Profit ({total_profit_points:.2f} points) exceeds threshold ({self.config.profit_points} points)")
                return True
            
            self.logger.info(f"RiskManager: Profit exit condition not met for {option_type}")
            return False
        except Exception as e:
            self.logger.error(f"RiskManager: Error checking profit exit condition: {str(e)}")
            # In case of error, don't trigger exit
            return False
    
    def calculate_position_profit_percentage(self, position):
        """
        Calculate profit percentage for a position
        
        Args:
            position: Position dictionary
            
        Returns:
            Profit percentage or None if calculation fails
        """
        try:
            if position['quantity'] == 0:
                return 0
            
            # For short positions
            if position['quantity'] < 0:
                entry_price = position['sell_price']
                current_price = self.order_manager.get_ltp(position['instrument_token'])
                
                if not current_price or not entry_price:
                    return None
                
                # For short positions, profit is when current price is lower than entry price
                profit_percentage = ((entry_price - current_price) / entry_price) * 100
                return profit_percentage
            
            # For long positions
            else:
                entry_price = position['buy_price']
                current_price = self.order_manager.get_ltp(position['instrument_token'])
                
                if not current_price or not entry_price:
                    return None
                
                # For long positions, profit is when current price is higher than entry price
                profit_percentage = ((current_price - entry_price) / entry_price) * 100
                return profit_percentage
        except Exception as e:
            self.logger.error(f"RiskManager: Error calculating position profit percentage: {str(e)}")
            return None
    
    def check_position_profit_threshold(self, position, threshold_percentage=25):
        """
        Check if a position has reached the profit threshold
        
        Args:
            position: Position dictionary
            threshold_percentage: Profit threshold percentage
            
        Returns:
            True if position has reached threshold, False otherwise
        """
        profit_percentage = self.calculate_position_profit_percentage(position)
        
        if profit_percentage is None:
            return False
        
        return profit_percentage >= threshold_percentage
    
    def check_position_loss_threshold(self, position, threshold_percentage=25):
        """
        Check if a position has reached the loss threshold
        
        Args:
            position: Position dictionary
            threshold_percentage: Loss threshold percentage
            
        Returns:
            True if position has reached threshold, False otherwise
        """
        profit_percentage = self.calculate_position_profit_percentage(position)
        
        if profit_percentage is None:
            return False
        
        return profit_percentage <= -threshold_percentage
    
    def is_trading_allowed(self):
        """
        Check if trading is allowed based on time, day, and holidays
        
        Returns:
            True if trading is allowed, False otherwise
        """
        now = datetime.datetime.now()
        today = now.date()
        current_time = now.time()
        weekday = now.strftime('%A')
        
        # Check if today is a holiday
        if today.strftime('%Y-%m-%d') in self.config.holiday_dates:
            self.logger.info(f"RiskManager: Today ({today}) is a holiday, trading not allowed")
            return False
        
        # Check if today is a special trading day
        if today.strftime('%Y-%m-%d') in self.config.special_trading_dates:
            self.logger.info(f"RiskManager: Today ({today}) is a special trading day")
            # Still need to check time
        else:
            # Check if today is a regular trading day
            if weekday not in self.config.trading_days:
                self.logger.info(f"RiskManager: Today ({weekday}) is not a trading day, trading not allowed")
                return False
        
        # Check trading hours
        start_time = datetime.datetime.strptime(self.config.start_time, "%H:%M:%S").time()
        end_time = datetime.datetime.strptime(self.config.end_time, "%H:%M:%S").time()
        
        if current_time < start_time or current_time > end_time:
            self.logger.info(f"RiskManager: Current time ({current_time}) is outside trading hours ({start_time} - {end_time}), trading not allowed")
            return False
        
        self.logger.info(f"RiskManager: Trading is allowed at {now}")
        return True
    
    def get_margin_utilization_percentage(self):
        """
        Get margin utilization as a percentage of allocated capital
        
        Returns:
            Margin utilization percentage or None if calculation fails
        """
        try:
            margin_used = self.order_manager.get_margin_used()
            
            if margin_used is None:
                return None
            
            utilization_percentage = (margin_used / self.capital_allocated) * 100
            self.logger.info(f"RiskManager: Current margin utilization: {utilization_percentage:.2f}%")
            return utilization_percentage
        except Exception as e:
            self.logger.error(f"RiskManager: Error calculating margin utilization: {str(e)}")
            return None
