import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from core.strategy import NiftyStrategy
from config import BIAS, ADJACENCY_GAP, LOT_SIZE
import pandas as pd

def mock_kite():
    class MockKite:
        def __init__(self):
            self.positions = {'net': []}
            self.orders = []
            self.instruments_cache = {}
            self.portfolio = {'positions': []}
            
        def instruments(self, exchange):
            if exchange == 'NFO':
                return self._generate_nifty_options()
            return pd.DataFrame()
            
        def _generate_nifty_options(self):
            current_date = datetime.now()
            expiries = self._generate_expiry_dates(current_date)
            strikes = self._generate_strikes()
            
            records = []
            for expiry in expiries:
                for strike in strikes:
                    for option_type in ['CE', 'PE']:
                        records.append({
                            'tradingsymbol': f'NIFTY25{expiry.strftime("%m%d")}{strike}{option_type}',
                            'expiry': expiry.date(),
                            'strike': strike,
                            'instrument_type': option_type
                        })
            return pd.DataFrame(records)
            
        def _generate_expiry_dates(self, base_date):
            monthly_expiries = [base_date + relativedelta(months=i, day=31) for i in range(4)]
            weekly_expiries = [base_date + timedelta(days=i) 
                             for i in range(7) if (base_date + timedelta(days=i)).weekday() == 3][:4]
            return sorted(monthly_expiries + weekly_expiries)
            
        def _generate_strikes(self):
            base = 18000
            return [base + i*100 for i in range(-10, 10)]
            
        def place_order(self, **kwargs):
            self.orders.append(kwargs)
            return f'ORDER_{len(self.orders)}'
            
    return MockKite()

@pytest.fixture
def strategy():
    kite = mock_kite()
    spot_price = 18250
    return NiftyStrategy(kite, spot_price)

def test_straddle_strategy_no_existing_positions(strategy):
    with patch('config.STRADDLE_FLAG', True), \
         patch('config.STRANGLE_FLAG', False):
        strategy.execute()
        
        orders = strategy.kite.orders
        assert len(orders) == 2
        assert all(o['transaction_type'] == 'SELL' for o in orders)
        assert any('CE' in o['tradingsymbol'] for o in orders)
        assert any('PE' in o['tradingsymbol'] for o in orders)

def test_strangle_strategy_position_conflict(strategy):
    with patch('config.STRANGLE_FLAG', True), \
         patch('config.STRADDLE_FLAG', False):
        # Create existing position conflict
        strategy.kite.positions['net'].append({
            'tradingsymbol': 'NIFTY25070418250CE',
            'product': 'MIS',
            'quantity': LOT_SIZE
        })
        
        strategy.execute()
        orders = strategy.kite.orders
        assert len(orders) == 2
        assert all(abs(int(o['tradingsymbol'][9:14]) - 18250) >= 1000 for o in orders)

def test_far_expiry_selection(strategy):
    far_expiry = strategy.get_far_expiry()
    current_date = datetime.now()
    expected_expiry = current_date + relativedelta(months=3, day=31)
    assert far_expiry == expected_expiry

def test_strike_adjustment_with_bias(strategy):
    with patch('config.BIAS', 50), \
         patch('config.STRADDLE_FLAG', True):
        strike = strategy.calculate_strikes('STRADDLE')
        assert strike == 18300

def test_profit_trigger_adjustment(strategy):
    with patch('core.strategy.config.PROFIT_POINTS', 250), \
         patch('core.strategy.config.FAR_SELL_ADD', True):
        # Simulate profitable position
        strategy.kite.portfolio['positions'].append({
            'unrealised': 300,
            'product': 'MIS'
        })
        
        strategy.manage_positions()
        orders = strategy.kite.orders
        assert any(o['order_type'] == 'SL' for o in orders)
        assert any(o['transaction_type'] == 'SELL' for o in orders)

def test_hedging_logic(strategy):
    with patch('config.BUY_HEDGE', True), \
         patch('config.HEDGE_ONE_LOT', True):
        # Simulate loss condition
        strategy.kite.portfolio['positions'].append({
            'unrealised': -150,
            'product': 'MIS'
        })
        
        strategy.execute_hedging()
        orders = strategy.kite.orders
        assert len(orders) == 1
        assert orders[0]['transaction_type'] == 'BUY'

def test_expiry_rollover(strategy):
    current_date = datetime.now()
    expiring_contract = current_date + timedelta(days=2)
    strategy.kite.positions['net'].append({
        'tradingsymbol': f'NIFTY25{expiring_contract.strftime("%m%d")}18000CE',
        'expiry': expiring_contract.date(),
        'product': 'MIS'
    })
    
    strategy.rollover_hedges()
    orders = strategy.kite.orders
    assert any('BUY' in o['transaction_type'] for o in orders)
    assert any('SELL' in o['transaction_type'] for o in orders)

def test_risk_shutdown(strategy):
    with patch('core.strategy.config.SHUTDOWN_LOSS', 12.5):
        strategy.kite.portfolio['positions'].append({
            'unrealised': -15.0,
            'product': 'MIS'
        })
        
        assert strategy.risk_manager.check_shutdown_triggers() is True
        strategy.risk_manager.execute_emergency_shutdown()
        assert len(strategy.kite.orders) > 0

def test_order_fallback_logic(strategy):
    original_place_order = strategy.kite.place_order
    strategy.kite.place_order = Mock(side_effect=Exception("API Error"))
    
    result = strategy.order_manager.place_order('NIFTY25XXXXX', 50, 'SELL')
    assert 'LIMIT' in result['order_type']
    
    strategy.kite.place_order = original_place_order

def test_instrument_selection_edge_cases(strategy):
    with patch('core.strategy.config.BIAS', 10000):
        strike = strategy.calculate_strikes('STRADDLE')
        assert strike == 28250  # Verifies upper boundary handling
        
    with patch('core.strategy.config.BIAS', -10000):
        strike = strategy.calculate_strikes('STRADDLE')
        assert strike == 8250  # Verifies lower boundary handling
