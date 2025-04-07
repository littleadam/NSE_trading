%%writefile /content/core/position_tracker.py
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

class PositionTracker:
    def __init__(self, kite_client):
        self.kite = kite_client
        self.positions = {}
        self._refresh()
        
    def _refresh(self):
        try:
            positions = self.kite.positions()['net']
            self.positions = {}
            for p in positions:
                if p['product'] == 'OPT':
                    key = p['tradingsymbol']
                    self.positions[key] = {
                        'quantity': abs(p['quantity']),
                        'average_price': p['average_price'],
                        'instrument_token': p['instrument_token'],
                        'option_type': 'CE' if 'CE' in key else 'PE',
                        'expiry': p['expiry']
                    }
        except Exception as e:
            logger.error(f"Position refresh failed: {str(e)}")
            raise
            
    def calculate_unrealized_loss_pct(self):
        total_investment = 0
        current_value = 0
        for symbol, pos in self.positions.items():
            ltp = self.kite.ltp(f"NFO:{symbol}")[f"NFO:{symbol}"]['last_price']
            total_investment += pos['average_price'] * pos['quantity']
            current_value += ltp * pos['quantity']
            
        if total_investment == 0:
            return 0
        return ((total_investment - current_value) / total_investment) * 100
