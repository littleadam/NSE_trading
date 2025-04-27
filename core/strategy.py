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
        atm_strike = round(adjusted_spot / self.config.strike_gap) * self.config.strike_gap
        
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
        ce_strike = round(ce_strike / self.config.strike_gap) * self.config.strike_gap
        pe_strike = round(pe_strike / self.config.strike_gap) * self.config.strike_gap
        
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
        ce_hedge_strike = round(ce_hedge_strike / self.config.strike_gap) * self.config.strike_gap
        pe_hedge_strike = round(pe_hedge_strike / self.config.strike_gap) * self.config.strike_gap
        
        self.logger.info(f"Strategy: Hedge strikes - CE: {ce_hedge_strike}, PE: {pe_hedge_strike}")
        
        # Get hedge instrument tokens
        ce_hedge_token = self.order_manager.get_instrument_token(next_weekly_expiry, ce_hedge_strike, "CE")
        pe_hedge_token = self.order_manager.get_instrument_token(next_weekly_expiry, pe_hedge_strike, "PE")
        
        if not ce_hedge_token or not pe_hedge_token:
            self.logger.error(f"Strategy: Could not find hedge instruments for expiry {next_weekly_expiry}")
            return
        
        # Calculate hedge quantity
        ce_hedge_quantity = self.config.lot_size if self.config.hedge_one_lot else self._calculate_hedge_quantity("CE")
        pe_hedge_quantity = self.config.lot_size if self.config.hedge_one_lot else self._calculate_hedge_quantity("PE")
        
        # Place hedge buy orders
        ce_hedge_order_id = self.order_manager.place_order(
            instrument_token=ce_hedge_token,
            transaction_type="BUY",
            quantity=ce_hedge_quantity,
            order_type="MARKET",
            tag="hedge_buy_ce"
        )
        
        pe_hedge_order_id = self.order_manager.place_order(
            instrument_token=pe_hedge_token,
            transaction_type="BUY",
            quantity=pe_hedge_quantity,
            order_type="MARKET",
            tag="hedge_buy_pe"
        )
        
        if ce_hedge_order_id and pe_hedge_order_id:
            self.logger.info(f"Strategy: Hedge buy orders placed successfully - CE: {ce_hedge_order_id}, PE: {pe_hedge_order_id}")
        else:
            self.logger.error("Strategy: Failed to place hedge buy orders")
    
    def _calculate_hedge_quantity(self, option_type):
        """
        Calculate hedge quantity based on sell quantity and active buy quantity
        
        Args:
            option_type: Option type (CE or PE)
            
        Returns:
            Hedge quantity
        """
        positions = self.order_manager.positions.get('net', [])
        
        # Calculate total sell quantity
        total_sell_quantity = 0
        for position in positions:
            if position['tradingsymbol'].endswith(option_type) and position['quantity'] < 0:
                total_sell_quantity += abs(position['quantity'])
        
        # Calculate active buy quantity
        active_buy_quantity = 0
        for position in positions:
            if position['tradingsymbol'].endswith(option_type) and position['quantity'] > 0:
                active_buy_quantity += position['quantity']
        
        # Calculate required hedge quantity
        hedge_quantity = total_sell_quantity - active_buy_quantity
        
        # Ensure minimum lot size
        if hedge_quantity <= 0:
            hedge_quantity = self.config.lot_size
        else:
            # Round to nearest lot size
            hedge_quantity = round(hedge_quantity / self.config.lot_size) * self.config.lot_size
        
        self.logger.info(f"Strategy: Calculated hedge quantity for {option_type}: {hedge_quantity} (total sell: {total_sell_quantity}, active buy: {active_buy_quantity})")
        return hedge_quantity
    
    def _manage_profitable_legs(self):
        """
        Check for profitable legs and add stop loss and new sell orders
        """
        self.logger.info("Strategy: Managing profitable legs")
        
        positions = self.order_manager.positions.get('net', [])
        
        for position in positions:
            # Only check short positions
            if position['quantity'] >= 0:
                continue
            
            # Check if position is in profit
            profit_percentage = self.risk_manager.calculate_position_profit_percentage(position)
            
            if profit_percentage is None:
                continue
            
            if profit_percentage >= self.config.profit_percentage:
                self.logger.info(f"Strategy: Position {position['tradingsymbol']} is in {profit_percentage:.2f}% profit, adding stop loss and new sell order")
                
                # Add stop loss
                self._add_stop_loss_for_position(position)
                
                # Add new sell order
                self._add_new_sell_order_for_profitable_leg(position)
    
    def _add_stop_loss_for_position(self, position):
        """
        Add stop loss for a profitable position
        
        Args:
            position: Position dictionary
        """
        # Calculate stop loss price
        entry_price = position['sell_price']
        stop_loss_price = entry_price * (self.config.stop_loss_percentage / 100)
        
        self.logger.info(f"Strategy: Setting stop loss for {position['tradingsymbol']} at {stop_loss_price:.2f} (entry: {entry_price:.2f})")
        
        # Find open orders for this position
        orders = self.order_manager.get_orders_for_instrument(position['instrument_token'])
        
        # Check if stop loss already exists
        sl_exists = any(order['transaction_type'] == 'BUY' and order['order_type'] in ['SL', 'SL-M'] for order in orders)
        
        if sl_exists:
            self.logger.info(f"Strategy: Stop loss already exists for {position['tradingsymbol']}")
            return
        
        # Place stop loss order
        order_id = self.order_manager.place_order(
            instrument_token=position['instrument_token'],
            transaction_type="BUY",
            quantity=abs(position['quantity']),
            order_type="SL-M",
            trigger_price=stop_loss_price,
            tag="stop_loss"
        )
        
        if order_id:
            self.logger.info(f"Strategy: Stop loss order placed successfully for {position['tradingsymbol']}, order_id: {order_id}")
        else:
            self.logger.error(f"Strategy: Failed to place stop loss order for {position['tradingsymbol']}")
    
    def _add_new_sell_order_for_profitable_leg(self, position):
        """
        Add new sell order for a profitable leg
        
        Args:
            position: Position dictionary
        """
        # Extract details from position
        tradingsymbol = position['tradingsymbol']
        instrument_token = position['instrument_token']
        
        # Find instrument details
        instrument = None
        for instr in self.order_manager.instruments_cache.values():
            if instr['instrument_token'] == instrument_token:
                instrument = instr
                break
        
        if not instrument:
            self.logger.error(f"Strategy: Could not find instrument details for {tradingsymbol}")
            return
        
        # Determine expiry and option type
        expiry = instrument['expiry']
        strike = instrument['strike']
        option_type = instrument['instrument_type']
        
        # Determine target expiry for new sell order
        if self.config.far_sell_add:
            # Use same expiry as the profitable sell order
            target_expiry = expiry
        else:
            # Use next week expiry
            target_expiry = self.expiry_manager.get_next_weekly_expiry()
        
        if not target_expiry:
            self.logger.error(f"Strategy: Could not determine target expiry for new sell order")
            return
        
        # Check if buy order exists at this strike
        if self._buy_order_exists_at_strike(target_expiry, strike, option_type):
            self.logger.warning(f"Strategy: Buy order exists at strike {strike}, adjusting strike")
            strike = self._adjust_strike_for_conflict(strike, -50 if option_type == "CE" else 50)
        
        # Get target instrument token
        target_token = self.order_manager.get_instrument_token(target_expiry, strike, option_type)
        
        if not target_token:
            self.logger.error(f"Strategy: Could not find target instrument for new sell order")
            return
        
        # Place new sell order (one lot)
        order_id = self.order_manager.place_order(
            instrument_token=target_token,
            transaction_type="SELL",
            quantity=self.config.lot_size,  # Always one lot
            order_type="MARKET",
            tag="additional_sell"
        )
        
        if order_id:
            self.logger.info(f"Strategy: New sell order placed successfully for {target_expiry}, {strike} {option_type}, order_id: {order_id}")
            
            # Place hedge buy order for the new sell order
            if self.config.buy_hedge:
                self._place_single_hedge_buy_order(target_token, option_type)
        else:
            self.logger.error(f"Strategy: Failed to place new sell order")
    
    def _place_single_hedge_buy_order(self, sell_token, option_type):
        """
        Place a single hedge buy order for a sell order
        
        Args:
            sell_token: Sell order instrument token
            option_type: Option type (CE or PE)
        """
        self.logger.info(f"Strategy: Placing single hedge buy order for {option_type}")
        
        # Get next weekly expiry
        next_weekly_expiry = self.expiry_manager.get_next_weekly_expiry()
        if not next_weekly_expiry:
            self.logger.error("Strategy: Could not determine next weekly expiry for hedge order")
            return
        
        # Get average premium of sell order
        sell_ltp = self.order_manager.get_ltp(sell_token)
        
        if not sell_ltp:
            self.logger.error("Strategy: Could not determine premium for hedge order")
            return
        
        # Get sell order details
        sell_instrument = None
        for instrument in self.order_manager.instruments_cache.values():
            if instrument['instrument_token'] == sell_token:
                sell_instrument = instrument
                break
        
        if not sell_instrument:
            self.logger.error("Strategy: Could not find instrument details for hedge order")
            return
        
        # Calculate hedge buy strike price
        if option_type == "CE":
            hedge_strike = sell_instrument['strike'] + sell_ltp
        else:  # PE
            hedge_strike = sell_instrument['strike'] - sell_ltp
        
        # Round to nearest 50 for Nifty
        hedge_strike = round(hedge_strike / self.config.strike_gap) * self.config.strike_gap
        
        self.logger.info(f"Strategy: Hedge strike for {option_type}: {hedge_strike}")
        
        # Get hedge instrument token
        hedge_token = self.order_manager.get_instrument_token(next_weekly_expiry, hedge_strike, option_type)
        
        if not hedge_token:
            self.logger.error(f"Strategy: Could not find hedge instrument for expiry {next_weekly_expiry}")
            return
        
        # Calculate hedge quantity
        hedge_quantity = self.config.lot_size if self.config.hedge_one_lot else self._calculate_hedge_quantity(option_type)
        
        # Place hedge buy order
        hedge_order_id = self.order_manager.place_order(
            instrument_token=hedge_token,
            transaction_type="BUY",
            quantity=hedge_quantity,
            order_type="MARKET",
            tag=f"hedge_buy_{option_type.lower()}"
        )
        
        if hedge_order_id:
            self.logger.info(f"Strategy: Hedge buy order placed successfully - {option_type}: {hedge_order_id}")
        else:
            self.logger.error(f"Strategy: Failed to place hedge buy order for {option_type}")
    
    def _manage_hedge_buy_orders(self):
        """
        Check for hedge buy orders in loss and add new sell orders
        """
        if not self.config.buy_hedge:
            return
        
        self.logger.info("Strategy: Managing hedge buy orders")
        
        positions = self.order_manager.positions.get('net', [])
        
        for position in positions:
            # Only check long positions
            if position['quantity'] <= 0:
                continue
            
            # Check if position is in loss
            loss_threshold = self.risk_manager.check_position_loss_threshold(position)
            
            if loss_threshold:
                self.logger.info(f"Strategy: Hedge position {position['tradingsymbol']} is in loss, adding new sell order")
                
                # Add new sell order at adjacency gap
                self._add_sell_order_for_hedge_in_loss(position)
    
    def _add_sell_order_for_hedge_in_loss(self, position):
        """
        Add new sell order for a hedge buy order in loss
        
        Args:
            position: Position dictionary
        """
        # Extract details from position
        tradingsymbol = position['tradingsymbol']
        instrument_token = position['instrument_token']
        
        # Find instrument details
        instrument = None
        for instr in self.order_manager.instruments_cache.values():
            if instr['instrument_token'] == instrument_token:
                instrument = instr
                break
        
        if not instrument:
            self.logger.error(f"Strategy: Could not find instrument details for {tradingsymbol}")
            return
        
        # Determine expiry, strike and option type
        expiry = instrument['expiry']
        strike = instrument['strike']
        option_type = instrument['instrument_type']
        
        # Calculate new strike with adjacency gap
        if option_type == "CE":
            new_strike = strike + self.config.adjacency_gap
        else:  # PE
            new_strike = strike - self.config.adjacency_gap
        
        # Round to nearest 50 for Nifty
        new_strike = round(new_strike / self.config.strike_gap) * self.config.strike_gap
        
        self.logger.info(f"Strategy: New strike for sell order: {new_strike} (original: {strike}, gap: {self.config.adjacency_gap})")
        
        # Check if buy order exists at this strike
        if self._buy_order_exists_at_strike(expiry, new_strike, option_type):
            self.logger.warning(f"Strategy: Buy order exists at strike {new_strike}, adjusting strike")
            new_strike = self._adjust_strike_for_conflict(new_strike, -1*self.config.strike_gap if option_type == "CE" else self.config.strike_gap)
        
        # Get new instrument token
        new_token = self.order_manager.get_instrument_token(expiry, new_strike, option_type)
        
        if not new_token:
            self.logger.error(f"Strategy: Could not find instrument for new sell order")
            return
        
        # Place new sell order
        order_id = self.order_manager.place_order(
            instrument_token=new_token,
            transaction_type="SELL",
            quantity=self.config.lot_size,
            order_type="MARKET",
            tag="hedge_loss_sell"
        )
        
        if order_id:
            self.logger.info(f"Strategy: New sell order placed successfully for {expiry}, {new_strike} {option_type}, order_id: {order_id}")
        else:
            self.logger.error(f"Strategy: Failed to place new sell order for hedge in loss")
    
    def _close_orphan_hedge_orders(self):
        """
        Close hedge buy orders that don't have corresponding sell orders
        """
        if not self.config.buy_hedge:
            return
        
        self.logger.info("Strategy: Checking for orphan hedge orders")
        
        positions = self.order_manager.positions.get('net', [])
        
        # Group positions by option type
        ce_positions = [p for p in positions if p['tradingsymbol'].endswith('CE')]
        pe_positions = [p for p in positions if p['tradingsymbol'].endswith('PE')]
        
        # Check CE positions
        ce_has_sell = any(p['quantity'] < 0 for p in ce_positions)
        ce_has_buy = any(p['quantity'] > 0 for p in ce_positions)
        
        if ce_has_buy and not ce_has_sell:
            self.logger.info("Strategy: Found orphan CE hedge orders, closing them")
            self._close_all_buy_positions_by_type("CE")
        
        # Check PE positions
        pe_has_sell = any(p['quantity'] < 0 for p in pe_positions)
        pe_has_buy = any(p['quantity'] > 0 for p in pe_positions)
        
        if pe_has_buy and not pe_has_sell:
            self.logger.info("Strategy: Found orphan PE hedge orders, closing them")
            self._close_all_buy_positions_by_type("PE")
    
    def _check_spot_price_touches_hedge(self):
        """
        Check if spot price touches hedge buy order strike and take action
        """
        if not self.config.buy_hedge or not self.nifty_spot_price:
            return
        
        self.logger.info("Strategy: Checking if spot price touches hedge buy order strike")
        
        positions = self.order_manager.positions.get('net', [])
        
        # Filter buy positions
        buy_positions = [p for p in positions if p['quantity'] > 0]
        
        for position in buy_positions:
            # Extract details from position
            tradingsymbol = position['tradingsymbol']
            instrument_token = position['instrument_token']
            
            # Find instrument details
            instrument = None
            for instr in self.order_manager.instruments_cache.values():
                if instr['instrument_token'] == instrument_token:
                    instrument = instr
                    break
            
            if not instrument:
                continue
            
            # Check if spot price is near the strike
            strike = instrument['strike']
            option_type = instrument['instrument_type']
            
            # Define "touching" as within 0.5% of the strike
            touch_threshold = 0.005 * strike
            
            if abs(self.nifty_spot_price - strike) <= touch_threshold:
                self.logger.info(f"Strategy: Spot price ({self.nifty_spot_price}) touches hedge strike ({strike}), closing hedge and adding far month orders")
                
                # Close the hedge
                self._close_position(position)
                
                # Add far month buy order
                self._add_far_month_buy_order(position)
    
    def _add_far_month_buy_order(self, position):
        """
        Add far month buy order to compensate for closed hedge
        
        Args:
            position: Position dictionary of the closed hedge
        """
        # Extract details from position
        tradingsymbol = position['tradingsymbol']
        instrument_token = position['instrument_token']
        
        # Find instrument details
        instrument = None
        for instr in self.order_manager.instruments_cache.values():
            if instr['instrument_token'] == instrument_token:
                instrument = instr
                break
        
        if not instrument:
            self.logger.error(f"Strategy: Could not find instrument details for {tradingsymbol}")
            return
        
        # Determine option type
        option_type = instrument['instrument_type']
        
        # Get far month expiry
        far_month_expiry = self.expiry_manager.get_far_month_expiry()
        if not far_month_expiry:
            self.logger.error("Strategy: Could not determine far month expiry")
            return
        
        # Get current premium of the position
        premium = self.order_manager.get_ltp(instrument_token)
        if not premium:
            self.logger.error(f"Strategy: Could not determine premium for {tradingsymbol}")
            return
        
        # Calculate target premium for far month (half of current premium)
        target_premium = premium / 2
        
        # Find a strike price that gives approximately the target premium
        target_strike = self._find_strike_for_premium(far_month_expiry, option_type, target_premium)
        if not target_strike:
            self.logger.error(f"Strategy: Could not find suitable strike for far month buy order")
            return
        
        # Get target instrument token
        target_token = self.order_manager.get_instrument_token(far_month_expiry, target_strike, option_type)
        if not target_token:
            self.logger.error(f"Strategy: Could not find instrument for far month buy order")
            return
        
        # Calculate quantity (2x the lot size of the closed hedge)
        quantity = 2 * abs(position['quantity'])
        
        # Place buy order
        order_id = self.order_manager.place_order(
            instrument_token=target_token,
            transaction_type="BUY",
            quantity=quantity,
            order_type="MARKET",
            tag="far_month_hedge_replacement"
        )
        
        if order_id:
            self.logger.info(f"Strategy: Far month buy order placed successfully for {far_month_expiry}, {target_strike} {option_type}, quantity: {quantity}, order_id: {order_id}")
        else:
            self.logger.error(f"Strategy: Failed to place far month buy order")
    
    def _find_strike_for_premium(self, expiry, option_type, target_premium):
        """
        Find a strike price that gives approximately the target premium
        
        Args:
            expiry: Expiry date
            option_type: Option type (CE or PE)
            target_premium: Target premium
            
        Returns:
            Strike price or None if not found
        """
        # Get ATM strike as a starting point
        atm_strike = self.get_atm_strike()
        if not atm_strike:
            return None
        
        # Define a range of strikes to check
        if option_type == "CE":
            # For CE, check strikes above ATM
            strikes_to_check = [atm_strike + i * self.config.strike_gap for i in range(20)]
        else:
            # For PE, check strikes below ATM
            strikes_to_check = [atm_strike - i * self.config.strike_gap for i in range(20)]
        
        best_strike = None
        best_diff = float('inf')
        
        for strike in strikes_to_check:
            # Get instrument token
            token = self.order_manager.get_instrument_token(expiry, strike, option_type)
            if not token:
                continue
            
            # Get premium
            premium = self.order_manager.get_ltp(token)
            if not premium:
                continue
            
            # Calculate difference from target
            diff = abs(premium - target_premium)
            
            # Update best if this is closer
            if diff < best_diff:
                best_diff = diff
                best_strike = strike
        
        return best_strike
    
    def _close_position(self, position):
        """
        Close a position
        
        Args:
            position: Position dictionary
        """
        # Determine transaction type (opposite of position)
        transaction_type = "SELL" if position['quantity'] > 0 else "BUY"
        
        # Place order to close position
        order_id = self.order_manager.place_order(
            instrument_token=position['instrument_token'],
            transaction_type=transaction_type,
            quantity=abs(position['quantity']),
            order_type="MARKET",
            tag="close_position"
        )
        
        if order_id:
            self.logger.info(f"Strategy: Position {position['tradingsymbol']} closed successfully, order_id: {order_id}")
        else:
            self.logger.error(f"Strategy: Failed to close position {position['tradingsymbol']}")
    
    def _exit_all_positions(self):
        """
        Exit all positions
        """
        self.logger.info("Strategy: Exiting all positions")
        
        positions = self.order_manager.positions.get('net', [])
        
        for position in positions:
            # Skip positions with zero quantity
            if position['quantity'] == 0:
                continue
            
            self._close_position(position)
    
    def _exit_all_positions_by_type(self, option_type):
        """
        Exit all positions of a specific option type
        
        Args:
            option_type: Option type (CE or PE)
        """
        self.logger.info(f"Strategy: Exiting all {option_type} positions")
        
        positions = self.order_manager.positions.get('net', [])
        
        for position in positions:
            # Skip positions with zero quantity or wrong type
            if position['quantity'] == 0 or not position['tradingsymbol'].endswith(option_type):
                continue
            
            self._close_position(position)
    
    def _close_all_buy_positions_by_type(self, option_type):
        """
        Close all buy positions of a specific option type
        
        Args:
            option_type: Option type (CE or PE)
        """
        self.logger.info(f"Strategy: Closing all {option_type} buy positions")
        
        positions = self.order_manager.positions.get('net', [])
        
        for position in positions:
            # Skip positions with zero or negative quantity or wrong type
            if position['quantity'] <= 0 or not position['tradingsymbol'].endswith(option_type):
                continue
            
            self._close_position(position)
    
    def _handle_expiry_day(self):
        """
        Handle operations on expiry day
        """
        self.logger.info("Strategy: Handling expiry day operations")
        
        # Get today's date
        today = datetime.datetime.now().date()
        
        # Refresh positions
        positions = self.order_manager.positions.get('net', [])
        
        # Find expiring buy positions
        expiring_buy_positions = []
        for position in positions:
            # Skip positions with zero or negative quantity
            if position['quantity'] <= 0:
                continue
            
            # Find instrument details
            instrument = None
            for instr in self.order_manager.instruments_cache.values():
                if instr['instrument_token'] == position['instrument_token']:
                    instrument = instr
                    break
            
            if not instrument:
                continue
            
            # Check if expiry is today
            if instrument['expiry'].date() == today:
                expiring_buy_positions.append(position)
        
        if not expiring_buy_positions:
            self.logger.info("Strategy: No expiring buy positions found")
            return
        
        self.logger.info(f"Strategy: Found {len(expiring_buy_positions)} expiring buy positions")
        
        # Group by option type
        ce_positions = [p for p in expiring_buy_positions if p['tradingsymbol'].endswith('CE')]
        pe_positions = [p for p in expiring_buy_positions if p['tradingsymbol'].endswith('PE')]
        
        # Replace CE positions
        if ce_positions:
            self._replace_expiring_buy_positions("CE", ce_positions)
        
        # Replace PE positions
        if pe_positions:
            self._replace_expiring_buy_positions("PE", pe_positions)
    
    def _replace_expiring_buy_positions(self, option_type, positions):
        """
        Replace expiring buy positions with new ones
        
        Args:
            option_type: Option type (CE or PE)
            positions: List of positions to replace
        """
        self.logger.info(f"Strategy: Replacing {len(positions)} expiring {option_type} buy positions")
        
        # Get next weekly expiry
        next_weekly_expiry = self.expiry_manager.get_next_weekly_expiry()
        if not next_weekly_expiry:
            self.logger.error("Strategy: Could not determine next weekly expiry")
            return
        
        # Calculate total quantity
        total_quantity = sum(p['quantity'] for p in positions)
        
        # Close expiring positions
        for position in positions:
            self._close_position(position)
        
        # Calculate new strike price based on average of sell positions
        sell_positions = [p for p in self.order_manager.positions.get('net', []) 
                          if p['quantity'] < 0 and p['tradingsymbol'].endswith(option_type)]
        
        if not sell_positions:
            self.logger.warning(f"Strategy: No {option_type} sell positions found to calculate hedge strike")
            # Use ATM strike as fallback
            atm_strike = self.get_atm_strike()
            if not atm_strike:
                self.logger.error("Strategy: Could not determine ATM strike")
                return
            
            new_strike = atm_strike
        else:
            # Calculate weighted average strike of sell positions
            total_sell_quantity = sum(abs(p['quantity']) for p in sell_positions)
            weighted_strike = sum(p['strike'] * abs(p['quantity']) for p in sell_positions) / total_sell_quantity
            
            # Round to nearest 50 for Nifty
            new_strike = round(weighted_strike / self.config.strike_gap) * self.config.strike_gap
        
        # Get average premium of sell positions
        sell_premiums = []
        for position in sell_positions:
            ltp = self.order_manager.get_ltp(position['instrument_token'])
            if ltp:
                sell_premiums.append(ltp)
        
        avg_premium = sum(sell_premiums) / len(sell_premiums) if sell_premiums else 0
        
        # Calculate hedge strike
        if option_type == "CE":
            hedge_strike = new_strike + avg_premium
        else:  # PE
            hedge_strike = new_strike - avg_premium
        
        # Round to nearest 50 for Nifty
        hedge_strike = round(hedge_strike / self.config.strike_gap) * self.config.strike_gap
        
        self.logger.info(f"Strategy: New hedge strike for {option_type}: {hedge_strike}")
        
        # Get hedge instrument token
        hedge_token = self.order_manager.get_instrument_token(next_weekly_expiry, hedge_strike, option_type)
        
        if not hedge_token:
            self.logger.error(f"Strategy: Could not find hedge instrument for expiry {next_weekly_expiry}")
            return
        
        # Place new hedge buy order
        order_id = self.order_manager.place_order(
            instrument_token=hedge_token,
            transaction_type="BUY",
            quantity=total_quantity,
            order_type="MARKET",
            tag=f"replacement_hedge_buy_{option_type.lower()}"
        )
        
        if order_id:
            self.logger.info(f"Strategy: Replacement hedge buy order placed successfully - {option_type}: {order_id}, quantity: {total_quantity}")
        else:
            self.logger.error(f"Strategy: Failed to place replacement hedge buy order for {option_type}")
    
    def _buy_order_exists_at_strike(self, expiry, strike, option_type):
        """
        Check if a buy order exists at the given strike
        
        Args:
            expiry: Expiry date
            strike: Strike price
            option_type: Option type (CE or PE)
            
        Returns:
            True if buy order exists, False otherwise
        """
        positions = self.order_manager.positions.get('net', [])
        
        for position in positions:
            # Skip positions with zero or negative quantity
            if position['quantity'] <= 0:
                continue
            
            # Find instrument details
            instrument = None
            for instr in self.order_manager.instruments_cache.values():
                if instr['instrument_token'] == position['instrument_token']:
                    instrument = instr
                    break
            
            if not instrument:
                continue
            
            # Check if this is the same strike, expiry, and option type
            if (instrument['expiry'] == expiry and 
                instrument['strike'] == strike and 
                instrument['instrument_type'] == option_type):
                return True
        
        return False
    
    def _adjust_strike_for_conflict(self, strike, adjustment):
        """
        Adjust strike price to avoid conflicts with existing orders
        
        Args:
            strike: Original strike price
            adjustment: Adjustment amount
            
        Returns:
            Adjusted strike price
        """
        new_strike = strike + adjustment
        return new_strike
