# position_manager.py
from typing import Dict, List, Optional
from datetime import datetime
from kite_utils import KiteManager
from reporting_manager import ReportingManager
from config import Config

class PositionManager:
    def __init__(self, kite_manager: KiteManager, config: Config):
        self.kite = kite_manager
        self.config = config
        self.reporting = ReportingManager(config)
        self.positions = {}
        self.original_premiums = {}
        self.stop_loss_orders = {}
        self.strategy_rules = {
            'profit_threshold': 0.75,
            'sl_threshold': 0.90,
            'buy_loss_threshold': 0.25,
            'min_premium': 100,
            'buy_cutoff': 30
        }
        self.logger = logging.getLogger(__name__)

    def _cleanup_orphan_sl_orders(self):
        """Remove SL orders without corresponding positions"""
        active_symbols = set(self.positions.keys())
        to_remove = []
        
        for symbol, sl_order in self.stop_loss_orders.items():
            if symbol not in active_symbols:
                try:
                    self.kite.cancel_order(sl_order['order_id'])
                    to_remove.append(symbol)
                    self.logger.info(f"Cancelled orphan SL order for {symbol}")
                except Exception as e:
                    self.logger.error(f"Failed to cancel SL order {sl_order['order_id']}: {str(e)}")
        
        for symbol in to_remove:
            del self.stop_loss_orders[symbol]

    def _log_position_state(self):
        """Log current positions and SL details"""
        position_log = {
            'timestamp': datetime.now().isoformat(),
            'positions': [],
            'sl_orders': []
        }
        
        for symbol, pos in self.positions.items():
            position_log['positions'].append({
                'symbol': symbol,
                'type': pos['type'],
                'strike': pos['strike'],
                'expiry': pos['expiry'],
                'quantity': pos['quantity'],
                'original_premium': pos['original_premium'],
                'current_premium': pos['current_premium'],
                'status': pos['status']
            })
        
        for symbol, sl in self.stop_loss_orders.items():
            position_log['sl_orders'].append({
                'symbol': symbol,
                'order_id': sl['order_id'],
                'trigger_price': sl['trigger_price'],
                'status': sl['status']
            })
        
        with open('position_state.log', 'a') as f:
            f.write(json.dumps(position_log) + '\n')

    def monitor_positions(self) -> List[Dict]:
        self._get_current_premiums()
        self._cleanup_orphan_sl_orders()
        actions = []
        
        for symbol in list(self.positions.keys()):
            # Check sell legs
            sell_action = self._check_sell_leg_conditions(symbol)
            if sell_action:
                actions.append(sell_action)
            
            # Check buy legs
            buy_action = self._check_buy_leg_conditions(symbol)
            if buy_action:
                actions.append(buy_action)
        
        self._log_position_state()
        return actions

    # ... (rest of the existing methods)
