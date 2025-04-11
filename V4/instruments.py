%%writefile instruments.py
import pickle
import os
from kiteconnect import KiteConnect
from tenacity import retry, stop_after_attempt
from config import config
from logger import setup_logger
from typing import Dict, List

log = setup_logger()

def filter_instruments(..., recursive_check=False):
    """Added recursive strike adjustment"""
    while True:
        filtered = [...]  # Existing logic
        if not recursive_check or not filtered:
            break
        strike -= config.STRIKE_ROUNDING
    return filtered

class InstrumentManager:
    def __init__(self):
        self.instruments = {}
        self.nifty_instruments = []
        self.load_instruments()

    @retry(stop=stop_after_attempt(3))
    def load_instruments(self):
        """Load instruments with retry logic"""
        log.info("Loading instruments")
        try:
            if os.path.exists('instruments.pkl'):
                log.debug("Loading from cache")
                with open('instruments.pkl', 'rb') as f:
                    self.instruments = pickle.load(f)
            else:
                log.debug("Fetching fresh instruments")
                kite = KiteConnect(api_key=config.API_KEY)
                all_instruments = kite.instruments()
                self.nifty_instruments = [
                    i for i in all_instruments 
                    if i['tradingsymbol'].startswith('NIFTY') 
                    and i['segment'] == 'NFO-OPT'
                ]
                self.instruments = {i['instrument_token']: i for i in self.nifty_instruments}
                with open('instruments.pkl', 'wb') as f:
                    pickle.dump(self.instruments, f)
            log.info(f"Loaded {len(self.instruments)} instruments")
        except Exception as e:
            log.error("Instrument loading failed", exc_info=True)
            raise
    
    def get_instrument(self, instrument_token: int) -> Dict:
        """Get instrument by token"""
        log.debug(f"Getting instrument {instrument_token}")
        return self.instruments.get(instrument_token)
    
    def get_spot_price(self) -> float:
        """Get current NIFTY spot price"""
        log.debug("Fetching spot price")
        try:
            kite = KiteConnect(api_key=config.API_KEY)
            ltp = kite.ltp('NSE:NIFTY 50')['NSE:NIFTY 50']['last_price']
            log.debug(f"Spot price: {ltp}")
            return ltp
        except Exception as e:
            log.error("Spot price fetch failed", exc_info=True)
            raise
