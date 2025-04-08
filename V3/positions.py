%%writefile positions.py
from kiteconnect import KiteConnect
from config import API_KEY, ACCESS_TOKEN
from utils import filter_instruments

class PositionManager:
    def __init__(self):
        self.kite = KiteConnect(api_key=API_KEY)
        self.kite.set_access_token(ACCESS_TOKEN)
        self.positions = {}
        self.orders = []
        self.spot_price = 0
        
    def sync_positions(self):
        self.positions = self.kite.positions()
        self.orders = self.kite.orders()
        self.spot_price = self.get_spot_price()
    
    def get_active_positions(self, strategy_type):
        active_positions = []
        for position in self.positions.get('net', []):
            if position['product'] != 'MIS':
                continue
            if strategy_type == 'straddle' and 'STRADDLE' in position['tag']:
                active_positions.append(position)
            elif strategy_type == 'strangle' and 'STRANGLE' in position['tag']:
                active_positions.append(position)
        return active_positions
    
    def calculate_unrealized_pnl(self):
        total_pnl = 0
        for position in self.positions.get('net', []):
            total_pnl += position['unrealised']
        return total_pnl
    
    def existing_position_check(self, expiry_date, strike, option_type):
        for position in self.positions.get('net', []):
            if (position['expiry'] == expiry_date and
                position['strike'] == strike and
                position['instrument_type'] == option_type):
                return True
        return False
