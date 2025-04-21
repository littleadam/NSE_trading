import os
import logging
import datetime
import pandas as pd
import numpy as np
from kiteconnect import KiteConnect

class Strategy:
    def __init__(self, kite, logger, config, order_manager, expiry_manager, risk_manager, streaming_service):
        """
        Initialize Strategy with required components
        
        Args:
            kite: Authenticated KiteConnect instance
            logger: Logger instance
            config: Configuration instance
            order_manager: OrderManager instance
            expiry_manager: ExpiryManager instance
            risk_manager: RiskManager instance
            streaming_service: StreamingService instance
        """
        self.kite = kite
        self.logger = logger
        self.config = config
        self.order_manager = order_manager
        self.expiry_manager = expiry_manager
        self.risk_manager = risk_manager
        self.streaming_service = streaming_service
        
        self.logger.info("Strategy: Initializing strategy module")
        
        # Initialize strategy state
        self.nifty_spot_price = None
        self.instruments_to_monitor = []
        
        self.logger.info("Strategy: Strategy module initialized")
    
    def update_spot_price(self):
        """
        Update Nifty spot price
        
        Returns:
            Current Nifty spot price
        """
        try:
            # Get Nifty 50 instrument token (hardcoded for now)
            nifty_instrument_token = 256265  # Nifty 50 index
            
            # Get LTP
            ltp_data = self.kite.ltp([f"NSE:NIFTY 50"])
            self.nifty_spot_price = ltp_data["NSE:NIFTY 50"]["last_price"]
            self.logger.info(f"Strategy: Updated Nifty spot price: {self.nifty_spot_price}")
            
            return self.nifty_spot_price
        except Exception as e:
            self.logger.error(f"Strategy: Failed to update Nifty spot price: {str(e)}")
            return None
    
    def get_atm_strike(self):
        """
        Get at-the-money strike price based on current spot price and bias
        
        Returns:
            ATM strike price
        """
        if not self.nifty_spot_price:
            self.update_spot_price()
            
            if not self.nifty_spot_price:
                self.logger.error("Strategy: Could not determine spot price for ATM strike calculation")
                return None
        
        # Apply bias to spot price
        adjusted_spot = self.nifty_spot_price + self.config.bias
        
        # Round to nearest 50 for Nifty
        atm_strike = round(adjusted_spot / 50) * 50
        
        self.logger.info(f"Strategy: ATM strike calculated as {atm_strike} (spot: {self.nifty_spot_price}, bias: {self.config.bias})")
        return atm_strike
    
    def execute(self):
        """
        Execute the strategy
        
        Returns:
            True if execution was successful, False otherwise
        """
        self.logger.info("Strategy: Starting strategy execution")
        
        # Check if trading is allowed
        if not self.risk_manager.is_trading_allowed():
            self.logger.info("Strategy: Trading not allowed at this time, skipping execution")
            return False
        
        # Check shutdown condition
        if self.risk_manager.check_shutdown_condition():
            self.logger.warning("Strategy: Shutdown condition met, exiting all positions")
            self._exit_all_positions()
            return False
        
        # Update spot price
        if not self.update_spot_price():
            self.logger.error("Strategy: Failed to update spot price, cannot execute strategy")
            return False
        
        # Refresh positions and orders
        self.order_manager.refresh_positions()
        self.order_manager.refresh_orders()
        
        # Check if we need to handle expiry day operations
        if self.expiry_manager.is_expiry_day():
            self.logger.info("Strategy: Today is an expiry day, handling expiry operations")
            self._handle_expiry_day()
        
        # Check profit exit conditions
        if self.risk_manager.check_profit_exit_condition(None, "CE"):
            self.logger.info("Strategy: Profit exit condition met for CE options, exiting all CE positions")
            self._exit_all_positions_by_type("CE")
        
        if self.risk_manager.check_profit_exit_condition(None, "PE"):
            self.logger.info("Strategy: Profit exit condition met for PE options, exiting all PE positions")
            self._exit_all_positions_by_type("PE")
        
        # Execute main strategy logic
        if self.config.straddle:
            self.logger.info("Strategy: Executing short straddle strategy")
            self._execute_short_straddle()
        elif self.config.strangle:
            self.logger.info("Strategy: Executing short strangle strategy")
            self._execute_short_strangle()
        else:
            self.logger.warning("Strategy: Neither straddle nor strangle strategy is enabled")
        
        # Check for profitable legs and add stop loss
        self._manage_profitable_legs()
        
        # Check for hedge buy orders in loss
        self._manage_hedge_buy_orders()
        
        # Check for orphan hedge orders
        self._close_orphan_hedge_orders()
        
        # Check if spot price touches hedge buy order strike
        self._check_spot_price_touches_hedge()
        
        self.logger.info("Strategy: Strategy execution completed")
        return True
    
    def _execute_short_straddle(self):
        """
        Execute short straddle strategy
        """
        # Get far month expiry
        far_month_expiry = self.expiry_manager.get_far_month_expiry()
        if not far_month_expiry:
            self.logger.error("Strategy: Could not determine far month expiry")
            return
        
        self.logger.info(f"Strategy: Far month expiry: {far_month_expiry}")
        
        # Check if short straddle already exists for far month expiry
        if self._short_straddle_exists(far_month_expiry):
            self.logger.info("Strategy: Short straddle already exists for far month expiry, skipping")
            return
        
        # Get ATM strike
        atm_strike = self.get_atm_strike()
        if not atm_strike:
            self.logger.error("Strategy: Could not determine ATM strike")
            return
        
        # Place sell orders for CE and PE at ATM strike
        self._place_short_straddle_orders(far_month_expiry, atm_strike)
    
    def _execute_short_strangle(self):
        """
        Execute short strangle strategy
        """
        # Get far month expiry
        far_month_expiry = self.expiry_manager.get_far_month_expiry()
        if not far_month_expiry:
            self.logger.error("Strategy: Could not determine far month expiry")
            return
        
        self.logger.info(f"Strategy: Far month expiry: {far_month_expiry}")
        
        # Check if short strangle already exists for far month expiry
        if self._short_strangle_exists(far_month_expiry):
            self.logger.info("Strategy: Short strangle already exists for far month expiry, skipping")
            return
        
        # Get ATM strike
        atm_strike = self.get_atm_strike()
        if not atm_strike:
            self.logger.error("Strategy: Could not determine ATM strike")
            return
        
        # Calculate strangle strikes (approximately 1000 points away from spot price)
        ce_strike = atm_strike + self.config.strangle_distance
        pe_strike = atm_strike - self.config.strangle_distance
        
        # Round to nearest 50 for Nifty
        ce_strike = round(ce_strike / 50) * 50
        pe_strike = round(pe_strike / 50) * 50
        
        self.logger.info(f"Strategy: Strangle strikes - CE: {ce_strike}, PE: {pe_strike}")
        
        # Place sell orders for CE and PE at calculated strikes
        self._place_short_strangle_orders(far_month_expiry, ce_strike, pe_strike)
    
    def _short_straddle_exists(self, expiry):
        """
        Check if a short straddle already exists for the given expiry
        
        Args:
            expiry: Expiry date to check
            
        Returns:
            True if short straddle exists, False otherwise
        """
        positions = self.order_manager.positions.get('net', [])
        
        # Filter positions by expiry
        expiry_str = expiry.strftime('%y%b').upper()
        expiry_positions = [p for p in positions if expiry_str in p['tradingsymbol']]
        
        # Check if we have both CE and PE short positions
        ce_short = any(p['quantity'] < 0 and p['tradingsymbol'].endswith('CE') for p in expiry_positions)
        pe_short = any(p['quantity'] < 0 and p['tradingsymbol'].endswith('PE') for p in expiry_positions)
        
        return ce_short and pe_short
    
    def _short_strangle_exists(self, expiry):
        """
        Check if a short strangle already exists for the given expiry
        
        Args:
            expiry: Expiry date to check
            
        Returns:
            True if short strangle exists, False otherwise
        """
        # For our purposes, the check is the same as for straddle
        return self._short_straddle_exists(expiry)
    
    def _place_short_straddle_orders(self, expiry, strike):
        """
        Place short straddle orders
        
        Args:
            expiry: Expiry date
            strike: Strike price
        """
        self.logger.info(f"Strategy: Placing short straddle orders for expiry {expiry}, strike {strike}")
        
        # Check if buy orders exist at this strike
        if self._buy_order_exists_at_strike(expiry, strike, "CE") or self._buy_order_exists_at_strike(expiry, strike, "PE"):
            self.logger.warning(f"Strategy: Buy order exists at strike {strike}, adjusting strike")
            strike = self._adjust_strike_for_conflict(strike, -50)  # Move to lower strike
        
        # Get instrument tokens
        ce_token = self.order_manager.get_instrument_token(expiry, strike, "CE")
        pe_token = self.order_manager.get_instrument_token(expiry, strike, "PE")
        
        if not ce_token or not pe_token:
            self.logger.error(f"Strategy: Could not find instruments for expiry {expiry}, strike {strike}")
            return
        
        # Place sell orders
        ce_order_id = self.order_manager.place_order(
            instrument_token=ce_token,
            transaction_type="SELL",
            quantity=self.config.lot_size,
            order_type="MARKET",
            tag="short_straddle_ce"
        )
        
        pe_order_id = self.order_manager.place_order(
            instrument_token=pe_token,
            transaction_type="SELL",
            quantity=self.config.lot_size,
            order_type="MARKET",
            tag="short_straddle_pe"
        )
        
        if ce_order_id and pe_order_id:
            self.logger.info(f"Strategy: Short straddle orders placed successfully - CE: {ce_order_id}, PE: {pe_order_id}")
            
            # Place hedge buy orders
            self._place_hedge_buy_orders(ce_token, pe_token)
        else:
            self.logger.error("Strategy: Failed to place short straddle orders")
    
    def _place_short_strangle_orders(self, expiry, ce_strike, pe_strike):
        """
        Place short strangle orders
        
        Args:
            expiry: Expiry date
            ce_strike: Strike price for CE
            pe_strike: Strike price for PE
        """
        self.logger.info(f"Strategy: Placing short strangle orders for expiry {expiry}, CE strike {ce_strike}, PE strike {pe_strike}")
        
        # Check if buy orders exist at these strikes
        if self._buy_order_exists_at_strike(expiry, ce_strike, "CE"):
            self.logger.warning(f"Strategy: Buy order exists at CE strike {ce_strike}, adjusting strike")
            ce_strike = self._adjust_strike_for_conflict(ce_strike, -50)  # Move to lower strike
        
        if self._buy_order_exists_at_strike(expiry, pe_strike, "PE"):
            self.logger.warning(f"Strategy: Buy order exists at PE strike {pe_strike}, adjusting strike")
            pe_strike = self._adjust_strike_for_conflict(pe_strike, 50)  # Move to higher strike
        
        # Get instrument tokens
        ce_token = self.order_manager.get_instrument_token(expiry, ce_strike, "CE")
        pe_token = self.order_manager.get_instrument_token(expiry, pe_strike, "PE")
        
        if not ce_token or not pe_token:
            self.logger.error(f"Strategy: Could not find instruments for expiry {expiry}, CE strike {ce_strike}, PE strike {pe_strike}")
            return
        
        # Place sell orders
        ce_order_id = self.order_manager.place_order(
            instrument_token=ce_token,
            transaction_type="SELL",
            quantity=self.config.lot_size,
            order_type="MARKET",
            tag="short_strangle_ce"
        )
        
        pe_order_id = self.order_manager.place_order(
            instrument_token=pe_token,
            transaction_type="SELL",
            quantity=self.config.lot_size,
            order_type="MARKET",
            tag="short_strangle_pe"
        )
        
        if ce_order_id and pe_order_id:
            self.logger.info(f"Strategy: Short strangle orders placed successfully - CE: {ce_order_id}, PE: {pe_order_id}")
            
            # Place hedge buy orders
            self._place_hedge_buy_orders(ce_token, pe_token)
        else:
            self.logger.error("Strategy: Failed to place short strangle orders")
    
    def _place_hedge_buy_orders(self, ce_token, pe_token):
        """
        Place hedge buy orders for the given sell orders
        
        Args:
            ce_token: CE instrument token
            pe_token: PE instrument token
        """
        if not self.config.buy_hedge:
            self.logger.info("Strategy: Buy hedge is disabled, skipping hedge orders")
            return
        
        self.logger.info("Strategy: Placing hedge buy orders")
        
        # Get next weekly expiry
        next_weekly_expiry = self.expiry_manager.get_next_weekly_expiry()
        if not next_weekly_expiry:
            self.logger.error("Strategy: Could not determine next weekly expiry for hedge orders")
            return
        
        # Get average premium of sell orders
        ce_ltp = self.order_manager.get_ltp(ce_token)
        pe_ltp = self.order_manager.get_ltp(pe_token)
        
        if not ce_ltp or not pe_ltp:
            self.logger.error("Strategy: Could not determine premiums for hedge orders")
            return
        
        # Get sell order details
        ce_instrument = None
        pe_instrument = None
        
        for instrument in self.order_manager.instruments_cache.values():
            if instrument['instrument_token'] == ce_token:
                ce_instrument = instrument
            elif instrument['instrument_token'] == pe_token:
                pe_instrument = instrument
        
        if not ce_instrument or not pe_instrument:
            self.logger.error("Strategy: Could not find instrument details for hedge orders")
            return
        
        # Calculate hedge buy strike prices
        # For CE: sell_strike + premium
        # For PE: sell_strike - premium
        ce_hedge_strike = ce_instrument['strike'] + ce_ltp
        pe_hedge_strike = pe_instrument['strike'] - pe_ltp
        
        # Round to nearest 50 for Nifty
        ce_hedge_strike = round(ce_hedge_strike / 50) * 50
        pe_hedge_strike = round(pe_hedge_strike / 50) * 50
        
        self.logger.info(f"Strategy: Hedge strikes - CE: {ce_hedge_strike}, PE: {pe_hedge_strike}")
        
        # Get hedge instrument tokens
        ce_hedge_token = self.order_manager.get_
(Content truncated due to size limit. Use line ranges to read in chunks)
