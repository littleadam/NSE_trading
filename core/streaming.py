import os
import logging
import pandas as pd
import datetime
import time
from kiteconnect import KiteTicker

class StreamingService:
    def __init__(self, kite, logger, instruments=None):
        """
        Initialize the streaming service with KiteConnect instance
        
        Args:
            kite: Authenticated KiteConnect instance
            logger: Logger instance
            instruments: List of instrument tokens to subscribe to
        """
        self.kite = kite
        self.logger = logger
        self.logger.info("StreamingService: Initializing streaming service")
        
        self.api_key = os.getenv('API_KEY')
        self.access_token = os.getenv('ACCESS_TOKEN')
        
        self.ticker = None
        self.instruments = instruments or []
        self.instrument_ltp = {}  # Store latest prices
        self.callbacks = {}  # Store callback functions
        self.is_connected = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.reconnect_interval = 5  # seconds
        
        self.logger.info(f"StreamingService: Ready to stream data for {len(self.instruments)} instruments")
    
    def start(self):
        """
        Start the WebSocket connection
        """
        self.logger.info("StreamingService: Starting WebSocket connection")
        
        if not self.instruments:
            self.logger.warning("StreamingService: No instruments to subscribe to")
            return False
        
        try:
            self.ticker = KiteTicker(self.api_key, self.access_token)
            
            # Register callbacks
            self.ticker.on_ticks = self.on_ticks
            self.ticker.on_connect = self.on_connect
            self.ticker.on_close = self.on_close
            self.ticker.on_error = self.on_error
            self.ticker.on_reconnect = self.on_reconnect
            self.ticker.on_noreconnect = self.on_noreconnect
            
            # Start the connection
            self.ticker.connect()
            return True
        except Exception as e:
            self.logger.error(f"StreamingService: Failed to start WebSocket connection: {str(e)}")
            return False
    
    def stop(self):
        """
        Stop the WebSocket connection
        """
        self.logger.info("StreamingService: Stopping WebSocket connection")
        if self.ticker:
            self.ticker.close()
            self.is_connected = False
            self.logger.info("StreamingService: WebSocket connection closed")
    
    def subscribe(self, instruments):
        """
        Subscribe to instruments
        
        Args:
            instruments: List of instrument tokens to subscribe to
        """
        if not instruments:
            self.logger.warning("StreamingService: No instruments to subscribe to")
            return
        
        self.instruments = instruments
        self.logger.info(f"StreamingService: Subscribing to {len(instruments)} instruments")
        
        if self.ticker and self.is_connected:
            try:
                self.ticker.subscribe(instruments)
                self.ticker.set_mode(self.ticker.MODE_FULL, instruments)
                self.logger.info(f"StreamingService: Subscribed to {len(instruments)} instruments")
            except Exception as e:
                self.logger.error(f"StreamingService: Failed to subscribe to instruments: {str(e)}")
    
    def unsubscribe(self, instruments):
        """
        Unsubscribe from instruments
        
        Args:
            instruments: List of instrument tokens to unsubscribe from
        """
        if not instruments:
            return
        
        self.logger.info(f"StreamingService: Unsubscribing from {len(instruments)} instruments")
        
        if self.ticker and self.is_connected:
            try:
                self.ticker.unsubscribe(instruments)
                # Remove from our instruments list
                self.instruments = [i for i in self.instruments if i not in instruments]
                self.logger.info(f"StreamingService: Unsubscribed from instruments")
            except Exception as e:
                self.logger.error(f"StreamingService: Failed to unsubscribe from instruments: {str(e)}")
    
    def register_callback(self, name, callback):
        """
        Register a callback function to be called when ticks are received
        
        Args:
            name: Name of the callback
            callback: Function to be called with ticks data
        """
        self.callbacks[name] = callback
        self.logger.info(f"StreamingService: Registered callback '{name}'")
    
    def unregister_callback(self, name):
        """
        Unregister a callback function
        
        Args:
            name: Name of the callback to unregister
        """
        if name in self.callbacks:
            del self.callbacks[name]
            self.logger.info(f"StreamingService: Unregistered callback '{name}'")
    
    def get_ltp(self, instrument_token):
        """
        Get the last traded price for an instrument
        
        Args:
            instrument_token: Instrument token
            
        Returns:
            Last traded price or None if not available
        """
        return self.instrument_ltp.get(instrument_token)
    
    def get_all_ltps(self):
        """
        Get all last traded prices
        
        Returns:
            Dictionary of instrument tokens and their last traded prices
        """
        return self.instrument_ltp.copy()
    
    # WebSocket callbacks
    def on_ticks(self, ws, ticks):
        """
        Callback when ticks are received
        """
        for tick in ticks:
            # Update our price cache
            self.instrument_ltp[tick['instrument_token']] = tick['last_price']
        
        # Call registered callbacks
        for name, callback in self.callbacks.items():
            try:
                callback(ticks)
            except Exception as e:
                self.logger.error(f"StreamingService: Error in callback '{name}': {str(e)}")
    
    def on_connect(self, ws, response):
        """
        Callback when connection is established
        """
        self.is_connected = True
        self.reconnect_attempts = 0
        self.logger.info("StreamingService: WebSocket connected")
        
        # Subscribe to instruments
        self.subscribe(self.instruments)
    
    def on_close(self, ws, code, reason):
        """
        Callback when connection is closed
        """
        self.is_connected = False
        self.logger.info(f"StreamingService: WebSocket closed: {reason} (code: {code})")
    
    def on_error(self, ws, code, reason):
        """
        Callback when error occurs
        """
        self.logger.error(f"StreamingService: WebSocket error: {reason} (code: {code})")
    
    def on_reconnect(self, ws, attempts_count):
        """
        Callback when reconnection is attempted
        """
        self.reconnect_attempts = attempts_count
        self.logger.info(f"StreamingService: WebSocket reconnecting, attempt {attempts_count}")
    
    def on_noreconnect(self, ws):
        """
        Callback when reconnection fails
        """
        self.logger.error("StreamingService: WebSocket failed to reconnect, max attempts reached")
        
        # Try to reconnect manually after some time
        if self.reconnect_attempts < self.max_reconnect_attempts:
            self.reconnect_attempts += 1
            self.logger.info(f"StreamingService: Manual reconnect attempt {self.reconnect_attempts} in {self.reconnect_interval} seconds")
            time.sleep(self.reconnect_interval)
            self.start()
        else:
            self.logger.error("StreamingService: Max manual reconnect attempts reached, giving up")
    
    def ensure_connection(self):
        """
        Ensure that the WebSocket connection is active
        
        Returns:
            True if connected, False otherwise
        """
        if not self.is_connected and self.reconnect_attempts < self.max_reconnect_attempts:
            self.logger.info("StreamingService: Connection not active, attempting to reconnect")
            self.reconnect_attempts += 1
            return self.start()
        
        return self.is_connected
