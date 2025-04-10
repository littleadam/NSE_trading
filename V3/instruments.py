%%writefile instruments.py
import pickle
import os
import requests
from kiteconnect import KiteConnect
from config import API_KEY
from tenacity import retry, stop_after_attempt

class InstrumentManager:
    def __init__(self):
        self.instruments = {}
        self.nifty_instruments = []
        self.load_instruments()

    @retry(stop=stop_after_attempt(3))
    def load_instruments(self):
        if os.path.exists('instruments.pkl'):
            with open('instruments.pkl', 'rb') as f:
                self.instruments = pickle.load(f)
        else:
            kite = KiteConnect(api_key=API_KEY)
            all_instruments = kite.instruments()
            self.nifty_instruments = [
                i for i in all_instruments 
                if i['tradingsymbol'].startswith('NIFTY') 
                and i['segment'] == 'NFO-OPT'
            ]
            self.instruments = {i['instrument_token']: i for i in self.nifty_instruments}
            with open('instruments.pkl', 'wb') as f:
                pickle.dump(self.instruments, f)
    
    def get_instrument(self, instrument_token):
        return self.instruments.get(instrument_token)
    
    def get_spot_price(self):
        kite = KiteConnect(api_key=API_KEY)
        return kite.ltp('NSE:NIFTY 50')['NSE:NIFTY 50']['last_price']
