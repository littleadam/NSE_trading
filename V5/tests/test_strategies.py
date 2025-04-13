# tests/test_strategies.py
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import pandas as pd
from kiteconnect import KiteConnect

from core.strategy import OptionsStrategy
from core.risk_manager import RiskManager
from core.order_manager import OrderManager
from core.expiry_manager import ExpiryManager
from core.streaming import DataStream
from utils.position_tracker import PositionTracker
import config

@pytest.fixture
def mock_kite():
    return Mock(spec=KiteConnect)

@pytest.fixture
def mock_order_manager(mock_kite):
    return OrderManager(mock_kite)

@pytest.fixture
def mock_risk_manager(mock_kite):
    return RiskManager(mock_kite)

@pytest.fixture
def sample_instruments():
    return pd.DataFrame([{
        'tradingsymbol': 'NIFTY23NOV18000CE',
        'instrument_token': 12345,
        'expiry': '2023-11-23',
        'strike': 18000,
        'instrument_type': 'CE',
        'name': 'NIFTY'
    }, {
        'tradingsymbol': 'NIFTY23NOV18000PE',
        'instrument_token': 12346,
        'expiry': '2023-11-23',
        'strike': 18000,
        'instrument_type': 'PE',
        'name': 'NIFTY'
    }])

def test_straddle_strike_calculation(mock_kite, sample_instruments):
    mock_kite.instruments.return_value = sample_instruments.to_dict('records')
    spot_price = 18000
    strategy = OptionsStrategy(mock_kite, spot_price)
    
    # Test with no bias
    straddle = strategy.calculate_straddle_strikes(datetime.now().date())
    assert straddle['ce'] == 18000
    assert straddle['pe'] == 18000
    
    # Test with positive bias
    config.Config.BIAS = 50
    straddle = strategy.calculate_straddle_strikes(datetime.now().date())
    assert straddle['ce'] == 18100
    assert straddle['pe'] == 17900

def test_emergency_shutdown_procedure(mock_kite, mock_risk_manager):
    # Mock pending orders and positions
    mock_kite.orders.return_value = [
        {'order_id': 1, 'status': 'OPEN'},
        {'order_id': 2, 'status': 'TRIGGER PENDING'}
    ]
    mock_kite.positions.return_value = {'net': [{
        'tradingsymbol': 'NIFTY23NOV18000CE',
        'quantity': -50,
        'product': 'MIS'
    }]}
    
    mock_risk_manager.execute_emergency_shutdown()
    
    # Verify order cancellations and position closing
    assert mock_kite.cancel_order.call_count == 2
    assert mock_kite.place_order.call_count >= 1

def test_expiry_rollover_logic(mock_kite, sample_instruments):
    expiry_mgr = ExpiryManager(mock_kite, Mock(), 18000)
    expiry_mgr.instruments = sample_instruments
    
    # Test near expiry hedge
    near_expiry = datetime.now().date() + timedelta(days=1)
    hedge = {
        'tradingsymbol': 'NIFTY23NOV18000CE',
        'expiry': near_expiry,
        'quantity': 50
    }
    
    assert expiry_mgr.needs_rollover(hedge) is True
    
    # Test valid hedge
    valid_expiry = datetime.now().date() + timedelta(days=3)
    hedge['expiry'] = valid_expiry
    assert expiry_mgr.needs_rollover(hedge) is False

def test_streaming_reconnection(mock_kite):
    stream = DataStream(mock_kite, 'api_key', 'access_token')
    stream.kws = Mock()
    
    # Simulate reconnection
    stream._on_reconnect(None)
    stream.kws.connect.assert_called_once()

def test_margin_calculation(mock_kite, mock_risk_manager):
    # Mock margin data
    mock_kite.margins.return_value = {
        'equity': {
            'net': 100000,
            'available': {'cash': 50000},
            'utilised': {'total': 50000}
        }
    }
    
    # Mock positions with P&L
    mock_risk_manager.position_tracker.positions = [{
        'unrealized_pnl': -15000
    }]
    
    assert mock_risk_manager._portfolio_loss_breached() is True  # 15% loss > 12.5% threshold

def test_order_conflict_detection(mock_kite, mock_order_manager):
    # Mock existing positions
    mock_kite.positions.return_value = {'net': [{
        'tradingsymbol': 'NIFTY23NOV18000CE',
        'strike': 18000,
        'expiry': '2023-11-23',
        'quantity': -50
    }]}
    
    # Test duplicate position check
    assert mock_order_manager._check_existing_positions(
        'STRADDLE', 18000, datetime.strptime('2023-11-23', '%Y-%m-%d').date()
    ) is True

def test_hedge_quantity_calculation(mock_kite):
    # Mock positions
    mock_kite.positions.return_value = {'net': [
        {'product': 'MIS', 'quantity': -100},
        {'product': 'NRML', 'quantity': 50}
    ]}
    
    expiry_mgr = ExpiryManager(mock_kite, Mock(), 18000)
    qty = expiry_mgr._calculate_hedge_quantity()
    
    assert qty == 50  # (100/2) = 50

def test_invalid_expiry_handling(mock_kite):
    strategy = OptionsStrategy(mock_kite, 18000)
    strategy.expiries = []  # No valid expiries
    
    with pytest.raises(ValueError):
        strategy.get_far_expiry()

def test_strangle_strike_validation(mock_kite):
    strategy = OptionsStrategy(mock_kite, 18000)
    
    # Test invalid strikes
    with pytest.raises(ValueError):
        strategy.calculate_strangle_strikes(
            datetime.now().date() + timedelta(days=7)
        )

def test_position_synchronization(mock_kite):
    tracker = PositionTracker(mock_kite)
    mock_kite.positions.return_value = {'net': []}
    
    tracker.update_positions()
    assert len(tracker.positions) == 0

def test_token_pruning_priority():
    stream = DataStream(Mock(), 'api_key', 'access_token')
    stream.subscribed_tokens = {12345, 67890}
    stream.instruments = {
        'NIFTY-CE': {'token': 12345},
        'BANKNIFTY-PE': {'token': 67890}
    }
    
    stream._prune_tokens()
    # Verify NIFTY instruments are retained
    assert 12345 in stream.subscribed_tokens

def test_profit_trigger_adjustment(mock_kite, mock_order_manager):
    position = {
        'entry_price': 100,
        'quantity': 50,
        'last_price': 125,
        'stop_loss_id': 'SL123'
    }
    
    mock_order_manager.adjust_orders_on_profit(position)
    mock_kite.modify_order.assert_called_with(
        order_id='SL123',
        trigger_price=90.0
    )

def test_configurable_strangle_gap():
    original_gap = config.Config.STRANGLE_GAP
    config.Config.STRANGLE_GAP = 1500
    
    strategy = OptionsStrategy(Mock(), 18000)
    assert strategy.calculate_strangle_strikes(
        datetime.now().date()
    )['ce'] >= 19500
    
    config.Config.STRANGLE_GAP = original_gap

def test_market_hours_check():
    # Test during market hours
    with patch('utils.helpers.Helpers.is_market_hours') as mock_hours:
        mock_hours.return_value = True
        assert Helpers.is_market_hours() is True
    
    # Test outside market hours
    with patch('utils.helpers.Helpers.is_market_hours') as mock_hours:
        mock_hours.return_value = False
        assert Helpers.is_market_hours() is False

def test_retry_logic():
    mock_func = Mock(side_effect=Exception('Failed'))
    decorated = Helpers.retry_api_call(max_retries=3)(mock_func)
    
    with pytest.raises(Exception):
        decorated()
    
    assert mock_func.call_count == 3

def teardown_module():
    import os
    if os.path.exists('instruments_cache.pkl'):
        os.remove('instruments_cache.pkl')
