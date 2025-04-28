import os
import logging
import datetime
import pandas as pd
from kiteconnect import KiteConnect

class OrderManager:
    def __init__(self, kite, logger, config):
        """
        Initialize OrderManager with KiteConnect instance
        
        Args:
            kite: Authenticated KiteConnect instance
            logger: Logger instance
            config: Configuration instance
        """
        self.kite = kite
        self.logger = logger
        self.config = config
        self.logger.info("OrderManager: Initializing order manager")
        
        # Cache for instruments
        self.instruments_cache = {}
        self.positions = {}
        self.orders = {}
        
        # Initialize cache
        self._init_instruments_cache()
        self.logger.info("OrderManager: Order manager initialized")
    
         def download_instruments(self):
         """
         Download instruments data and save to CSV
         
         Returns:
             True if successful, False otherwise
         """
         try:
             self.logger.info("OrderManager: Downloading instruments data")
             
             # Create directory if it doesn't exist
             os.makedirs('data', exist_ok=True)
             
             # Download instruments
             instruments = self.kite.instruments("NFO")
             
             # Save to CSV
             df = pd.DataFrame(instruments)
             df.to_csv('data/instruments.csv', index=False)
             
             self.logger.info(f"OrderManager: Downloaded {len(instruments)} instruments")
             return True
         except Exception as e:
             self.logger.error(f"OrderManager: Failed to download instruments: {str(e)}")
             return False
    
     def load_instruments_from_csv(self):
         """
         Load instruments from CSV file
         
         Returns:
             List of instruments or None if failed
         """
         try:
             csv_path = 'data/instruments.csv'
             if not os.path.exists(csv_path):
                 self.logger.warning("OrderManager: Instruments CSV not found, downloading")
                 if not self.download_instruments():
                     return None
             
             # Load CSV
             df = pd.read_csv(csv_path)
             
             # Convert to list of dictionaries
             instruments = df.to_dict('records')
             
             # Convert expiry strings to datetime
             for instrument in instruments:
                 if 'expiry' in instrument and instrument['expiry']:
                     try:
                         instrument['expiry'] = pd.to_datetime(instrument['expiry']).to_pydatetime()
                     except:
                         pass
             
             self.logger.info(f"OrderManager: Loaded {len(instruments)} instruments from CSV")
             return instruments
         except Exception as e:
             self.logger.error(f"OrderManager: Failed to load instruments from CSV: {str(e)}")
             return None
    
     def get_lot_size(self, instrument_token):
         """
         Get lot size for an instrument
         
         Args:
             instrument_token: Instrument token
             
         Returns:
             Lot size or None if not found
         """
         try:
             # Find instrument in cache
             for instrument in self.instruments_cache.values():
                 if instrument['instrument_token'] == instrument_token:
                     lot_size = instrument.get('lot_size')
                     if lot_size:
                         return lot_size
             
             # If not found in cache, use default
             return self.config.lot_size
         except Exception as e:
             self.logger.error(f"OrderManager: Failed to get lot size: {str(e)}")
             return self.config.lot_size
    
     def _init_instruments_cache(self):
         """
         Initialize instruments cache
         """
         try:
             self.logger.info("OrderManager: Initializing instruments cache")
             
             # Try to load from CSV first
             instruments = self.load_instruments_from_csv()
             
             # If CSV loading failed, fetch from API
             if not instruments:
                 instruments = self._api_call_with_retry(self.kite.instruments, "NFO")
             
             if not instruments:
                 self.logger.error("OrderManager: Failed to initialize instruments cache")
                 return
             
             # Filter for NIFTY options
             nifty_instruments = [i for i in instruments if i['name'] == 'NIFTY']
             
             # Build cache
             self.instruments_cache = {}
             for instrument in nifty_instruments:
                 if 'expiry' in instrument and instrument['strike'] and instrument['instrument_type'] in ['CE', 'PE']:
                     key = f"{instrument['expiry'].strftime('%Y-%m-%d')}_{instrument['strike']}_{instrument['instrument_type']}"
                     self.instruments_cache[key] = instrument
             
             self.logger.info(f"OrderManager: Initialized instruments cache with {len(self.instruments_cache)} instruments")
         except Exception as e:
             self.logger.error(f"OrderManager: Error initializing instruments cache: {str(e)}")
    
     def _api_call_with_retry(self, func, *args, **kwargs):
         """
         Make API call with retry
         
         Args:
             func: Function to call
             *args: Positional arguments
             **kwargs: Keyword arguments
             
         Returns:
             Result of function call or None if all retries failed
         """
         retries = 0
         while retries < self.config.max_retries:
             try:
                 return func(*args, **kwargs)
             except Exception as e:
                 retries += 1
                 self.logger.warning(f"OrderManager: API call failed (attempt {retries}/{self.config.max_retries}): {str(e)}")
                 if retries < self.config.max_retries:
                     time.sleep(self.config.retry_delay)
                 else:
                     self.logger.error(f"OrderManager: All retries failed for API call: {str(e)}")
                     return None
    
    def _create_instrument_key(self, expiry, strike, instrument_type):
        """
        Create a unique key for instrument cache lookup
        
        Args:
            expiry: Expiry date (datetime.date)
            strike: Strike price (float)
            instrument_type: CE or PE
            
        Returns:
            String key for cache lookup
        """
        if isinstance(expiry, datetime.datetime):
            expiry = expiry.date()
        elif isinstance(expiry, str):
            expiry = datetime.datetime.strptime(expiry, "%Y-%m-%d").date()
        
        return f"{expiry.strftime('%Y-%m-%d')}_{strike}_{instrument_type}"
    
    def get_instrument(self, expiry, strike, instrument_type):
        """
        Get instrument details from cache
        
        Args:
            expiry: Expiry date (datetime.date)
            strike: Strike price (float)
            instrument_type: CE or PE
            
        Returns:
            Instrument details or None if not found
        """
        key = self._create_instrument_key(expiry, strike, instrument_type)
        instrument = self.instruments_cache.get(key)
        
        if not instrument:
            self.logger.warning(f"OrderManager: Instrument not found in cache: {key}")
            # Try to refresh cache
            self._init_instruments_cache()
            instrument = self.instruments_cache.get(key)
            
            if not instrument:
                self.logger.error(f"OrderManager: Instrument not found even after cache refresh: {key}")
                return None
        
        return instrument
    
    def get_instrument_token(self, expiry, strike, instrument_type):
        """
        Get instrument token for given parameters
        
        Args:
            expiry: Expiry date (datetime.date)
            strike: Strike price (float)
            instrument_type: CE or PE
            
        Returns:
            Instrument token or None if not found
        """
        instrument = self.get_instrument(expiry, strike, instrument_type)
        if instrument:
            return instrument['instrument_token']
        return None
    
    def refresh_positions(self):
        """
        Refresh positions from Kite API
        
        Returns:
            Dictionary of positions
        """
        try:
            self.logger.info("OrderManager: Refreshing positions")
            positions = self.kite.positions()
            
            # Store positions
            self.positions = positions
            
            self.logger.info(f"OrderManager: Refreshed positions: {len(positions['net'])} net positions")
            return positions
        except Exception as e:
            self.logger.error(f"OrderManager: Failed to refresh positions: {str(e)}")
            return None
    
    def refresh_orders(self):
        """
        Refresh orders from Kite API
        
        Returns:
            List of orders
        """
        try:
            self.logger.info("OrderManager: Refreshing orders")
            orders = self.kite.orders()
            
            # Store orders
            self.orders = {order['order_id']: order for order in orders}
            
            self.logger.info(f"OrderManager: Refreshed orders: {len(orders)} orders")
            return orders
        except Exception as e:
            self.logger.error(f"OrderManager: Failed to refresh orders: {str(e)}")
            return None
    
    def get_position_for_instrument(self, instrument_token):
        """
        Get position for a specific instrument
        
        Args:
            instrument_token: Instrument token
            
        Returns:
            Position details or None if not found
        """
        if not self.positions:
            self.refresh_positions()
        
        for position in self.positions.get('net', []):
            if position['instrument_token'] == instrument_token:
                return position
        
        return None
    
    def get_orders_for_instrument(self, instrument_token):
        """
        Get orders for a specific instrument
        
        Args:
            instrument_token: Instrument token
            
        Returns:
            List of orders for the instrument
        """
        if not self.orders:
            self.refresh_orders()
        
        return [order for order in self.orders.values() if order['instrument_token'] == instrument_token]
    
    def place_order(self, instrument_token, transaction_type, quantity, order_type="MARKET", price=0, trigger_price=0, tag=None):
        """
        Place an order
        
        Args:
            instrument_token: Instrument token
            transaction_type: BUY or SELL
            quantity: Order quantity
            order_type: Order type (MARKET, LIMIT, SL, SL-M)
            price: Order price (for LIMIT orders)
            trigger_price: Trigger price (for SL, SL-M orders)
            tag: Tag for the order
            
        Returns:
            Order ID if successful, None otherwise
        """
        try:
            self.logger.info(f"OrderManager: Placing {transaction_type} order for {quantity} of {instrument_token}")
            
            params = {
                "tradingsymbol": self._get_trading_symbol_from_token(instrument_token),
                "exchange": "NFO",
                "transaction_type": transaction_type,
                "quantity": quantity,
                "order_type": order_type,
                "product": "NRML",  # Use NRML for F&O
            }
            
            if order_type in ["LIMIT", "SL"]:
                params["price"] = price
            
            if order_type in ["SL", "SL-M"]:
                params["trigger_price"] = trigger_price
            
            if tag:
                params["tag"] = tag
            
            order_id = self.kite.place_order(variety="regular", **params)
            self.logger.info(f"OrderManager: Order placed successfully, order_id: {order_id}")
            
            # Refresh orders to include the new order
            self.refresh_orders()
            
            return order_id
        except Exception as e:
            self.logger.error(f"OrderManager: Failed to place order: {str(e)}")
            
            # If market order fails, try limit order
            if order_type == "MARKET":
                self.logger.info("OrderManager: Attempting to place limit order instead")
                try:
                    # Get current market price
                    ltp = self.kite.ltp([instrument_token])[str(instrument_token)]['last_price']
                    
                    # Adjust price based on transaction type
                    if transaction_type == "BUY":
                        price = ltp * 1.01  # 1% higher than LTP
                    else:  # SELL
                        price = ltp * 0.99  # 1% lower than LTP
                    
                    return self.place_order(
                        instrument_token=instrument_token,
                        transaction_type=transaction_type,
                        quantity=quantity,
                        order_type="LIMIT",
                        price=price,
                        tag=tag
                    )
                except Exception as e2:
                    self.logger.error(f"OrderManager: Failed to place limit order as fallback: {str(e2)}")
            
            return None
    
    def modify_order(self, order_id, price=None, trigger_price=None, quantity=None, order_type=None):
        """
        Modify an existing order
        
        Args:
            order_id: Order ID to modify
            price: New price (optional)
            trigger_price: New trigger price (optional)
            quantity: New quantity (optional)
            order_type: New order type (optional)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.logger.info(f"OrderManager: Modifying order {order_id}")
            
            params = {}
            if price is not None:
                params["price"] = price
            if trigger_price is not None:
                params["trigger_price"] = trigger_price
            if quantity is not None:
                params["quantity"] = quantity
            if order_type is not None:
                params["order_type"] = order_type
            
            self.kite.modify_order(variety="regular", order_id=order_id, **params)
            self.logger.info(f"OrderManager: Order {order_id} modified successfully")
            
            # Refresh orders to include the modified order
            self.refresh_orders()
            
            return True
        except Exception as e:
            self.logger.error(f"OrderManager: Failed to modify order {order_id}: {str(e)}")
            return False
    
    def cancel_order(self, order_id):
        """
        Cancel an existing order
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.logger.info(f"OrderManager: Cancelling order {order_id}")
            self.kite.cancel_order(variety="regular", order_id=order_id)
            self.logger.info(f"OrderManager: Order {order_id} cancelled successfully")
            
            # Refresh orders to reflect the cancellation
            self.refresh_orders()
            
            return True
        except Exception as e:
            self.logger.error(f"OrderManager: Failed to cancel order {order_id}: {str(e)}")
            return False
    
    def _get_trading_symbol_from_token(self, instrument_token):
        """
        Get trading symbol from instrument token
        
        Args:
            instrument_token: Instrument token
            
        Returns:
            Trading symbol or None if not found
        """
        # Search in cache
        for instrument in self.instruments_cache.values():
            if instrument['instrument_token'] == instrument_token:
                return instrument['tradingsymbol']
        
        # If not found, try to get from API
        try:
            instruments = self.kite.instruments("NFO")
            for instrument in instruments:
                if instrument['instrument_token'] == instrument_token:
                    return instrument['tradingsymbol']
        except Exception as e:
            self.logger.error(f"OrderManager: Failed to get trading symbol for token {instrument_token}: {str(e)}")
        
        return None
    
    def get_order_status(self, order_id):
        """
        Get status of an order
        
        Args:
            order_id: Order ID
            
        Returns:
            Order status or None if not found
        """
        if not self.orders:
            self.refresh_orders()
        
        order = self.orders.get(order_id)
        if order:
            return order['status']
        
        return None
    
    def is_order_complete(self, order_id):
        """
        Check if an order is complete
        
        Args:
            order_id: Order ID
            
        Returns:
            True if order is complete, False otherwise
        """
        status = self.get_order_status(order_id)
        return status == "COMPLETE"
    
    def is_order_rejected(self, order_id):
        """
        Check if an order is rejected
        
        Args:
            order_id: Order ID
            
        Returns:
            True if order is rejected, False otherwise
        """
        status = self.get_order_status(order_id)
        return status == "REJECTED"
    
    def get_order_average_price(self, order_id):
        """
        Get average price of an executed order
        
        Args:
            order_id: Order ID
            
        Returns:
            Average price or None if order not complete
        """
        if not self.orders:
            self.refresh_orders()
        
        order = self.orders.get(order_id)
        if order and order['status'] == "COMPLETE":
            return order['average_price']
        
        return None
    
    def get_ltp(self, instrument_token):
        """
        Get last traded price for an instrument
        
        Args:
            instrument_token: Instrument token
            
        Returns:
            Last traded price or None if not available
        """
        try:
            ltp_data = self.kite.ltp([instrument_token])
            return ltp_data[str(instrument_token)]['last_price']
        except Exception as e:
            self.logger.error(f"OrderManager: Failed to get LTP for {instrument_token}: {str(e)}")
            return None
    
    def get_margin_used(self):
        """
        Get margin used
        
        Returns:
            Margin used or None if not available
        """
        try:
            margins = self.kite.margins()
            return margins['equity']['utilised']['total']
        except Exception as e:
            self.logger.error(f"OrderManager: Failed to get margin used: {str(e)}")
            return None
