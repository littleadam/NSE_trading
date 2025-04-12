# core/streaming.py
import logging
from kiteconnect import KiteTicker
from threading import Lock
import json
from utils.logger import configure_logger
from config import LOT_SIZE, TRADE_DAYS

configure_logger()
logger = logging.getLogger(__name__)

class DataStream:
    def __init__(self, kite_client, api_key, access_token):
        self.kite = kite_client
        self.api_key = api_key
        self.access_token = access_token
        self.kws = None
        self.instruments = {}
        self.price_data = {}
        self.lock = Lock()
        self.subscribed_tokens = set()
        self.active = False
        self.nifty_token = 256265  # Nifty 50 index token

        # Initialize instrument mapping
        self._load_instruments()

    def _load_instruments(self):
        """Cache all NFO instruments for fast lookup"""
        try:
            instruments = self.kite.instruments('NFO')
            for instr in instruments:
                key = f"{instr['tradingsymbol']}-{instr['instrument_type']}"
                self.instruments[key] = {
                    'token': instr['instrument_token'],
                    'strike': instr['strike'],
                    'expiry': instr['expiry']
                }
            logger.info(f"Loaded {len(instruments)} NFO instruments")
        except Exception as e:
            logger.error(f"Instrument loading failed: {str(e)}")
            raise

    def _get_instrument_token(self, tradingsymbol, instrument_type):
        key = f"{tradingsymbol}-{instrument_type}"
        return self.instruments.get(key, {}).get('token')

    def start_stream(self):
        """Initialize WebSocket connection with error handling"""
        try:
            self.kws = KiteTicker(self.api_key, self.access_token)
            self.kws.on_connect = self._on_connect
            self.kws.on_close = self._on_close
            self.kws.on_reconnect = self._on_reconnect
            self.kws.on_ticks = self._on_ticks
            self.kws.on_error = self._on_error
            
            self.kws.connect(threaded=True)
            self.active = True
            logger.info("WebSocket connection initiated")
        except Exception as e:
            logger.error(f"WebSocket connection failed: {str(e)}")
            self.active = False

    def _on_connect(self, ws, response):
        """Handle connection success"""
        logger.info("WebSocket connected")
        self.subscribe([self.nifty_token])

    def _on_close(self, ws, code, reason):
        """Handle connection closure"""
        logger.warning(f"WebSocket closed: Code {code}, Reason: {reason}")
        self.active = False

    def _on_reconnect(self, ws):
        """Handle automatic reconnection"""
        logger.info("WebSocket reconnecting...")
        self.subscribed_tokens.clear()

    def _on_error(self, ws, error):
        """Handle WebSocket errors"""
        logger.error(f"WebSocket error: {str(error)}")

    def _on_ticks(self, ws, ticks):
        """Process incoming ticks with thread safety"""
        with self.lock:
            for tick in ticks:
                token = tick['instrument_token']
                self.price_data[token] = {
                    'timestamp': tick['timestamp'],
                    'last_price': tick['last_price'],
                    'oi': tick['oi'],
                    'volume': tick['volume_traded'],
                    'bid_qty': tick['depth']['buy'][0]['quantity'],
                    'bid_price': tick['depth']['buy'][0]['price'],
                    'ask_qty': tick['depth']['sell'][0]['quantity'],
                    'ask_price': tick['depth']['sell'][0]['price']
                }
            logger.debug(f"Updated {len(ticks)} ticks")

    def subscribe(self, tokens):
        """Subscribe to instruments with connection checks"""
        if not self.active:
            logger.warning("Cannot subscribe - connection inactive")
            return

        new_tokens = [t for t in tokens if t not in self.subscribed_tokens]
        if new_tokens:
            try:
                self.kws.subscribe(new_tokens)
                self.subscribed_tokens.update(new_tokens)
                logger.info(f"Subscribed to tokens: {new_tokens}")
            except Exception as e:
                logger.error(f"Subscription failed: {str(e)}")

    def unsubscribe(self, tokens):
        """Unsubscribe from specific instruments"""
        if self.active and tokens:
            try:
                self.kws.unsubscribe(tokens)
                self.subscribed_tokens.difference_update(tokens)
                logger.info(f"Unsubscribed from tokens: {tokens}")
            except Exception as e:
                logger.error(f"Unsubscription failed: {str(e)}")

    def get_spot_price(self):
        """Get current Nifty spot price"""
        return self.price_data.get(self.nifty_token, {}).get('last_price')

    def get_option_data(self, tradingsymbol, instrument_type):
        """Get complete market data for specific option contract"""
        token = self._get_instrument_token(tradingsymbol, instrument_type)
        if not token:
            logger.error(f"Instrument not found: {tradingsymbol} {instrument_type}")
            return None
        
        data = self.price_data.get(token, {})
        if not data:
            return None

        return {
            'tradingsymbol': tradingsymbol,
            'type': instrument_type,
            'last_price': data.get('last_price'),
            'bid': data.get('bid_price'),
            'ask': data.get('ask_price'),
            'oi': data.get('oi'),
            'volume': data.get('volume')
        }

    def add_strategy_instruments(self, strategies):
        """Subscribe to instruments for active strategies"""
        tokens = []
        for strategy in strategies:
            for leg in strategy['legs']:
                token = self._get_instrument_token(leg['tradingsymbol'], leg['type'])
                if token:
                    tokens.append(token)
        
        if tokens:
            self.subscribe(tokens)

    def stop(self):
        """Graceful shutdown of WebSocket connection"""
        if self.active:
            self.kws.close()
            self.active = False
            logger.info("WebSocket connection stopped")
