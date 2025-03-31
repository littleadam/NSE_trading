# strategy_manager.py
from position_manager import PositionManager
from kite_utils import KiteManager
from iron_fly_strategy import IronFlyStrategy
from config import Config

class StrategyManager:
    def __init__(self, kite_manager: KiteManager, config: Config):
        self.kite = kite_manager
        self.config = config
        self.position_manager = PositionManager(kite_manager, config)
        self.iron_fly = IronFlyStrategy()
        self.reporting = ReportingManager()
        self.is_running = False
        self.monthly_stats = {
            'orders_placed': 0,
            'pnl': 0
        }

    def _handle_sl_execution(self, order_details: Dict):
        """Process executed SL orders"""
        # Calculate P&L for this SL execution
        symbol = order_details['tradingsymbol']
        position = self.position_manager.positions.get(symbol)
        
        if position:
            pnl = (position['original_premium'] - order_details['average_price']) * position['quantity']
            order_details['pnl'] = pnl
            self.monthly_stats['pnl'] += pnl
            
            # Update position status
            self.position_manager.update_position_status(symbol, 'SL_EXECUTED')
            
            # Log to reporting system
            self.reporting.log_sl_execution(order_details)

    def _update_monthly_stats(self):
        """Update monthly statistics"""
        self.reporting.update_monthly_stats(
            self.monthly_stats['orders_placed'],
            self.monthly_stats['pnl']
        )
        self.monthly_stats = {'orders_placed': 0, 'pnl': 0}  # Reset for next period

    def start_strategy(self):
        self.is_running = True
        current_month = datetime.now().month
        
        try:
            # Initialize strategy
            params = self.iron_fly.get_strategy_parameters()
            strategy_legs = self._setup_initial_positions(params)
            self.position_manager.initialize_positions(strategy_legs)
            
            # Start monitoring loop
            while self.is_running:
                # Check for month change
                if datetime.now().month != current_month:
                    self._update_monthly_stats()
                    current_month = datetime.now().month
                
                actions = self.position_manager.monitor_positions()
                self._handle_actions(actions, params)
                time.sleep(60)  # Check every minute
                
        except Exception as e:
            print(f"Strategy failed: {str(e)}")
            self.is_running = False
        finally:
            self._update_monthly_stats()

    def _setup_initial_positions(self, params: Dict) -> List[Dict]:
        # Similar to previous execute_iron_fly logic
        # Returns list of position dictionaries
        pass

    def _handle_actions(self, actions: List[Dict], params: Dict):
        for action in actions:
            if action['action'] == 'ADD_SELL':
                self._handle_add_sell(action, params)
            elif action['action'] == 'HEDGE_BUY':
                self._handle_hedge_buy(action, params)

    def _handle_add_sell(self, action: Dict, params: Dict):
        # Create new sell position
        new_symbol = self.kite.create_option_symbol(
            'BANKNIFTY',
            action['expiry'],
            action['strike'],
            'CE' if 'CE' in action['symbol'] else 'PE'
        )
        
        # Place order
        order_id = self.kite.place_market_order(
            new_symbol, 'NFO', 'SELL', params['lot_size']
        )
        
        # Update position manager
        self.position_manager.add_new_position({
            'symbol': new_symbol,
            'type': 'SELL',
            'strike': action['strike'],
            'expiry': action['expiry'],
            'quantity': params['lot_size'],
            'original_premium': action['premium'],
            'current_premium': action['premium'],
            'status': 'ACTIVE'
        })

    def _handle_hedge_buy(self, action: Dict, params: Dict):
        # Find next OTM strike
        # Implement your strike selection logic here
        new_strike = action['strike'] + 100  # Example
        
        # Create hedge symbol
        hedge_symbol = self.kite.create_option_symbol(
            'BANKNIFTY',
            action['expiry'],
            new_strike,
            'PE' if 'PE' in action['symbol'] else 'CE'
        )
        
        # Place sell order
        order_id = self.kite.place_market_order(
            hedge_symbol, 'NFO', 'SELL', params['lot_size']
        )
        
        # Update position manager
        self.position_manager.add_new_position({
            'symbol': hedge_symbol,
            'type': 'SELL',
            'strike': new_strike,
            'expiry': action['expiry'],
            'quantity': params['lot_size'],
            'original_premium': self.kite.get_ltp([hedge_symbol])[hedge_symbol]['last_price'],
            'current_premium': None,
            'status': 'ACTIVE'
        })

    def stop_strategy(self):
        self.is_running = False
