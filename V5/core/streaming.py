# core/streaming.py
import logging
from kiteconnect import KiteTicker
from threading import Lock, Timer
import time
from typing import Dict, Set, List, Optional
from datetime import datetime
from config import Config
from utils.helpers import Helpers
from utils.logger import DecisionLogger

logger = logging.getLogger(__name__)

class DataStream:
    def __init__(self, kite_client, api_key: str, access_token: str):
        self.kite = kite_client
        self.api_key = api_key
        self.access_token = access_token
        self.kws: Optional[KiteTicker] = None
        self.instruments: Dict = {}
        self.price_data: Dict = {}
        self.lock = Lock()
        self.subscribed_tokens: Set[int] = set()
        self.active = False
        self.nifty_token: Optional[int] = None
        self.max_retries = 3
        self.retry_count = 0
        self.token_limit = Config.WS_TOKEN_LIMIT  # From config
        self.last_heartbeat = time.time()
        self._initialize_stream()

    def _initialize_stream(self):
        """Initialize stream with proper error handling"""
        try:
            self._load_instruments()
            if not self.nifty_token:
                logger.critical("Failed to initialize NIFTY 50 token")
                raise ValueError("NIFTY 50 instrument not found")
            logger.info("Stream initialized with %d instruments", len(self.instruments))
        except Exception as e:
            logger.critical(f"Stream initialization failed: {str(e)}")
            raise RuntimeError("Data stream setup failed") from e

    def _load_instruments(self):
        """Cache all instruments with proper Nifty token identification"""
        try:
            # Load NSE instruments for index token
            nse_instruments = self.kite.instruments('NSE')
            self.nifty_token = self._find_nifty_token(nse_instruments)

            # Load NFO instruments for derivatives
            nfo_instruments = self.kite.instruments('NFO')
            self._cache_nfo_instruments(nfo_instruments)
            logger.info(f"Loaded {len(nfo_instruments)} NFO instruments")
        except Exception as e:
            logger.error(f"Instrument loading failed: {str(e)}")
            raise

    def _find_nifty_token(self, instruments: List[Dict]) -> int:
        """Identify NIFTY 50 token from NSE instruments"""
        for instr in instruments:
            if instr['tradingsymbol'] == 'NIFTY 50':
                return instr['instrument_token']
        raise ValueError("NIFTY 50 instrument not found in NSE listings")

    def _cache_nfo_instruments(self, instruments: List[Dict]):
        """Cache NFO instruments with standardized keys"""
        for instr in instruments:
            key = f"{instr['tradingsymbol']}-{instr['instrument_type']}"
            self.instruments[key] = {
                'token': instr['instrument_token'],
                'strike': instr['strike'],
                'expiry': instr['expiry']
            }

    def _get_instrument_token(self, tradingsymbol: str, instrument_type: str) -> Optional[int]:
        """Safe instrument token lookup with validation"""
        key = f"{tradingsymbol}-{instrument_type}"
        return self.instruments.get(key, {}).get('token')

    def start_stream(self):
        """Robust WebSocket connection with retry logic"""
        try:
            if self.active:
                logger.warning("Stream already active")
                return

            self.kws = KiteTicker(self.api_key, self.access_token)
            self._setup_handlers()
            
            while self.retry_count < self.max_retries:
                try:
                    self.kws.connect(threaded=True)
                    self.active = True
                    self.retry_count = 0
                    logger.info("WebSocket connection established")
                    DecisionLogger.log_decision({"event": "websocket_connected"})
                    return
                except Exception as e:
                    self.retry_count += 1
                    wait_time = 2 ** self.retry_count
                    logger.warning(f"Connection failed (attempt {self.retry_count}), retrying in {wait_time}s")
                    time.sleep(wait_time)
            
            logger.error("Max connection retries exceeded")
            self.active = False
            DecisionLogger.log_decision({"event": "websocket_retries_exhausted"})

        except Exception as e:
            logger.critical(f"Stream startup failed: {str(e)}")
            self.active = False
            DecisionLogger.log_decision({"event": "websocket_startup_failed", "error": str(e)})

    def _setup_handlers(self):
        """Configure WebSocket event handlers"""
        self.kws.on_connect = self._on_connect
        self.kws.on_close = self._on_close
        self.kws.on_reconnect = self._on_reconnect
        self.kws.on_ticks = self._on_ticks
        self.kws.on_error = self._on_error

    def _on_connect(self, ws, response):
        """Handle successful connection"""
        logger.info("WebSocket connected")
        DecisionLogger.log_decision({"event": "websocket_connected"})
        
        # Resubscribe to previous tokens
        if self.subscribed_tokens:
            self._batch_subscribe(list(self.subscribed_tokens))
        
        # Subscribe to Nifty spot if available
        if self.nifty_token:
            self.subscribe([self.nifty_token])

    def _batch_subscribe(self, tokens: List[int]):
        """Handle token subscription in batches"""
        try:
            for i in range(0, len(tokens), self.token_limit):
                batch = tokens[i:i+self.token_limit]
                self.kws.subscribe(batch)
                logger.info(f"Resubscribed to {len(batch)} tokens")
                DecisionLogger.log_decision({"event": "batch_subscribed", "count": len(batch)})
        except Exception as e:
            logger.error(f"Batch subscribe failed: {str(e)}")
            DecisionLogger.log_decision({"event": "batch_subscribe_failed", "error": str(e)})

    def _on_close(self, ws, code: int, reason: str):
        """Handle connection closure"""
        logger.warning(f"WebSocket closed - Code: {code}, Reason: {reason}")
        self.active = False
        DecisionLogger.log_decision({"event": "websocket_closed", "code": code, "reason": reason})

    def _on_reconnect(self, ws):
        """Handle automatic reconnection"""
        logger.info("WebSocket reconnecting...")
        self.active = False
        DecisionLogger.log_decision({"event": "websocket_reconnecting"})
        Timer(1, self.start_stream).start()  # Delay before reconnect

    def _on_error(self, ws, error: str):
        """Handle WebSocket errors"""
        logger.error(f"WebSocket error: {error}")
        DecisionLogger.log_decision({"event": "websocket_error", "error": error})
        self._reconnect()

    def _reconnect(self):
        """Explicit reconnection handler"""
        logger.info("Initiating manual reconnect")
        self.active = False
        self.retry_count = 0
        self.start_stream()

    def _on_ticks(self, ws, ticks: List[Dict]):
        """Process incoming ticks with error resilience"""
        with self.lock:
            # Update heartbeat timestamp
            self.last_heartbeat = time.time()
            
            # Check for Zerodha heartbeat (token = -1)
            if any(tick.get('instrument_token', 0) == -1 for tick in ticks):
                logger.info("Received WebSocket heartbeat")
                if (time.time() - self.last_heartbeat) > 60:
                    logger.warning("Stale heartbeat detected, reconnecting")
                    self._reconnect()
                return

            # Circuit breaker for stale data
            if self._is_data_stale(ticks):
                logger.warning("Stale tick data detected, pausing strategies")
                DecisionLogger.log_decision({"event": "data_stale"})
                self._reconnect()
                return

            try:
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
                logger.debug(f"Processed {len(ticks)} ticks")
            except KeyError as e:
                logger.warning(f"Malformed tick data: Missing {str(e)}")
                DecisionLogger.log_decision({"event": "malformed_tick", "error": str(e)})
            except Exception as e:
                logger.error(f"Tick processing error: {str(e)}")
                DecisionLogger.log_decision({"event": "tick_processing_error", "error": str(e)})

    def _is_data_stale(self, ticks: List[Dict]) -> bool:
        """Check if tick data is older than 60 seconds"""
        if not ticks:
            return False
        try:
            newest_tick = max(t['timestamp'] for t in ticks if 'timestamp' in t)
            return (datetime.now().timestamp() - newest_tick.timestamp()) > 60
        except Exception as e:
            logger.error(f"Stale check failed: {str(e)}")
            return True

    def subscribe(self, tokens: List[int]):
        """Safe subscription with connection checks and token management"""
        if not self.active:
            logger.warning("Subscribe attempted on inactive connection")
            return

        new_tokens = [t for t in tokens if t not in self.subscribed_tokens]
        if not new_tokens:
            return

        try:
            # Respect token limit with priority preservation
            if len(self.subscribed_tokens) + len(new_tokens) > self.token_limit:
                logger.warning(f"Token limit reached ({self.token_limit}), pruning oldest 25%")
                self._prune_tokens()

            self.kws.subscribe(new_tokens)
            self.subscribed_tokens.update(new_tokens)
            logger.info(f"Subscribed to {len(new_tokens)} new tokens")
            DecisionLogger.log_decision({"event": "tokens_subscribed", "count": len(new_tokens)})
        except Exception as e:
            logger.error(f"Subscription failed: {str(e)}")
            DecisionLogger.log_decision({"event": "subscription_failed", "error": str(e)})

    def _prune_tokens(self):
        """Priority-based token pruning with NIFTY protection"""
        token_priority = {
            t: (2 if t == self.nifty_token else
                1 if self._is_strategy_instrument(t) else
                0)
            for t in self.subscribed_tokens
        }

        # Sort by priority (descending) then by timestamp (ascending)
        lru_tokens = sorted(
            self.subscribed_tokens,
            key=lambda t: (
                -token_priority[t],
                self.price_data.get(t, {}).get('timestamp', 0)
            )
        )[int(self.token_limit * 0.25):]

        self.unsubscribe(lru_tokens)

    def _is_strategy_instrument(self, token: int) -> bool:
        """Check if token belongs to a NIFTY derivative"""
        symbol = self._get_symbol(token)
        return symbol.startswith('NIFTY') and symbol != 'NIFTY 50'

    def _get_symbol(self, token: int) -> str:
        """Get tradingsymbol from cached instruments"""
        for key, data in self.instruments.items():
            if data['token'] == token:
                return key.split('-')[0]
        return 'UNKNOWN'

    def unsubscribe(self, tokens: List[int]):
        """Unsubscribe from specific tokens"""
        if self.active and tokens:
            try:
                self.kws.unsubscribe(tokens)
                self.subscribed_tokens.difference_update(tokens)
                logger.info(f"Unsubscribed from {len(tokens)} tokens")
                DecisionLogger.log_decision({"event": "tokens_unsubscribed", "count": len(tokens)})
            except Exception as e:
                logger.error(f"Unsubscription failed: {str(e)}")
                DecisionLogger.log_decision({"event": "unsubscription_failed", "error": str(e)})

    def get_spot_price(self) -> Optional[float]:
        """Get current Nifty spot price with validation"""
        try:
            return self.price_data[self.nifty_token]['last_price']
        except KeyError:
            logger.warning("Nifty spot price not available")
            DecisionLogger.log_decision({"event": "spot_price_unavailable"})
            return None

    def get_option_data(self, tradingsymbol: str, instrument_type: str) -> Optional[Dict]:
        """Comprehensive option data retrieval"""
        token = self._get_instrument_token(tradingsymbol, instrument_type)
        if not token:
            logger.error(f"Instrument not found: {tradingsymbol} {instrument_type}")
            DecisionLogger.log_decision({"event": "instrument_not_found", 
                                       "symbol": tradingsymbol, 
                                       "type": instrument_type})
            return None
        
        with self.lock:
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
                'volume': data.get('volume'),
                'timestamp': data.get('timestamp')
            }

    def add_strategy_instruments(self, strategies: List[Dict]):
        """Batch subscribe to strategy instruments"""
        tokens = []
        for strategy in strategies:
            for leg in strategy.get('legs', []):
                token = self._get_instrument_token(leg['tradingsymbol'], leg['type'])
                if token and token not in self.subscribed_tokens:
                    tokens.append(token)
        
        if tokens:
            self.subscribe(tokens)

    def stop(self):
        """Graceful shutdown with retry logic"""
        retries = 0
        while self.active and retries < 3:
            try:
                if self.kws:
                    self.kws.close()
                self.active = False
                logger.info("WebSocket connection closed")
                DecisionLogger.log_decision({"event": "websocket_stopped"})
                break
            except Exception as e:
                retries += 1
                logger.error(f"Shutdown failed (attempt {retries}): {str(e)}")
                DecisionLogger.log_decision({"event": "shutdown_failed", 
                                           "attempt": retries, 
                                           "error": str(e)})
                time.sleep(1)
