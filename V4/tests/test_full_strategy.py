%%writefile test_full_strategy.py
import sys
import os
import pytest
from unittest.mock import Mock, patch, MagicMock
import datetime
from datetime import date, timedelta
import pandas as pd

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import all application modules
from config import config
from strategies import OptionStrategy
from utils import (
    is_market_open,
    get_expiry_date,
    round_strike,
    calculate_quantity,
    filter_instruments,
    calculate_profit_points
)
from orders import OrderManager
from positions import PositionManager
from instruments import InstrumentManager

# ==================== Test Configuration ====================
@pytest.fixture
def mock_strategy():
    """Fixture for OptionStrategy with mocked dependencies"""
    with patch('positions.PositionManager'), \
         patch('orders.OrderManager'), \
         patch('instruments.InstrumentManager'):
        strategy = OptionStrategy()
        strategy.position_manager = Mock(spec=PositionManager)
        strategy.order_manager = Mock(spec=OrderManager)
        strategy.instrument_manager = Mock(spec=InstrumentManager)
        strategy.spot_price = 21500
        yield strategy

# ==================== Core Functionality Tests ====================
def test_straddle_entry_logic(mock_strategy):
    """Test straddle entry with proper strike calculation"""
    # Setup
    mock_strategy.instrument_manager.nifty_instruments = [
        {'tradingsymbol': 'NIFTY25JAN21500CE', 'strike': 21500, 'expiry': '2024-01-25', 'instrument_type': 'CE'},
        {'tradingsymbol': 'NIFTY25JAN21500PE', 'strike': 21500, 'expiry': '2024-01-25', 'instrument_type': 'PE'}
    ]
    mock_strategy.position_manager.get_active_positions.return_value = []
    mock_strategy.position_manager.kite.margins.return_value = {'equity': {'available': {'cash': 500000}}}
    
    # Execute
    mock_strategy.manage_straddle()
    
    # Verify
    assert mock_strategy.order_manager.place_order.call_count == 2
    calls = mock_strategy.order_manager.place_order.call_args_list
    assert 'CE' in calls[0][1]['tag']
    assert 'PE' in calls[1][1]['tag']

def test_strangle_entry_1000pts(mock_strategy):
    """Test strangle placement at ±1000 points from spot"""
    # Setup
    config.STRANGLE_DISTANCE = 1000
    mock_strategy.instrument_manager.nifty_instruments = [
        {'tradingsymbol': 'NIFTY25JAN22500CE', 'strike': 22500, 'expiry': '2024-01-25', 'instrument_type': 'CE'},
        {'tradingsymbol': 'NIFTY25JAN20500PE', 'strike': 20500, 'expiry': '2024-01-25', 'instrument_type': 'PE'}
    ]
    mock_strategy.position_manager.get_active_positions.return_value = []
    
    # Execute
    mock_strategy.manage_strangle()
    
    # Verify
    assert mock_strategy.order_manager.place_order.call_count == 2
    calls = mock_strategy.order_manager.place_order.call_args_list
    assert calls[0][1]['instrument']['strike'] == 22500
    assert calls[1][1]['instrument']['strike'] == 20500

# ==================== Risk Management Tests ====================
def test_shutdown_condition(mock_strategy):
    """Test shutdown when loss exceeds threshold"""
    # Setup
    mock_strategy.position_manager.calculate_unrealized_pnl.return_value = -150000
    mock_strategy.position_manager.kite.margins.return_value = {'equity': {'available': {'cash': 1000000}}}
    config.SHUTDOWN_LOSS = 0.125  # 12.5%
    
    # Execute
    result = mock_strategy.check_shutdown_condition()
    
    # Verify
    assert result is True
    mock_strategy.close_all_positions.assert_called_once()

def test_profit_booking_25percent(mock_strategy):
    """Test profit booking at 25% threshold"""
    # Setup
    mock_position = Mock(
        quantity=-1,
        average_price=100,
        last_price=75,  # 25% profit
        instrument_type='CE',
        order_id='TEST123'
    )
    mock_strategy.position_manager.positions = {'net': [mock_position]}
    config.PROFIT_THRESHOLD = 0.25
    
    # Execute
    mock_strategy.manage_profit_booking()
    
    # Verify
    mock_strategy.order_manager.modify_order.assert_called_once()
    assert mock_strategy.order_manager.place_order.call_count == 1

# ==================== Expiry Management Tests ====================
def test_monthly_expiry_rollover(mock_strategy):
    """Test monthly to weekly rollover logic"""
    # Setup
    mock_position = Mock(
        quantity=-1,
        average_price=100,
        strike=21500,
        expiry='2024-01-25',
        instrument_type='CE',
        tag='STRADDLE_CE'
    )
    mock_strategy.position_manager.positions = {'net': [mock_position]}
    mock_strategy.instrument_manager.get_instrument.return_value = {
        'tradingsymbol': 'NIFTY01FEB21500CE',
        'strike': 21500,
        'expiry': '2024-02-01'
    }
    
    # Execute
    mock_strategy.manage_expiry_rollover()
    
    # Verify
    assert mock_strategy.order_manager.place_order.call_count == 2  # Close + reopen

# ==================== Edge Case Tests ====================
def test_insufficient_margin(mock_strategy):
    """Test quantity calculation with insufficient margin"""
    # Setup
    mock_strategy.position_manager.kite.margins.return_value = {'equity': {'available': {'cash': 50000}}}
    config.MARGIN_PER_LOT = 120000
    
    # Execute
    qty = calculate_quantity(50000)
    
    # Verify
    assert qty == 0
    mock_strategy.order_manager.place_order.assert_not_called()

def test_missing_instruments(mock_strategy):
    """Test behavior when required instruments are missing"""
    # Setup
    mock_strategy.instrument_manager.nifty_instruments = []
    
    # Execute
    mock_strategy.manage_straddle()
    
    # Verify
    mock_strategy.order_manager.place_order.assert_not_called()

# ==================== Utility Function Tests ====================
def test_round_strike():
    """Test strike price rounding logic"""
    config.STRIKE_ROUNDING = 50
    assert round_strike(21237) == 21200
    assert round_strike(21250) == 21250
    assert round_strike(21263) == 21250

def test_expiry_date_calculation():
    """Test expiry date calculation logic"""
    # Test monthly expiry (last Thursday)
    test_date = date(2024, 1, 1)
    expiry = get_expiry_date('monthly', test_date)
    assert expiry.month == test_date.month
    assert expiry.weekday() == 3  # Thursday
    
    # Test weekly expiry (next Thursday)
    expiry = get_expiry_date('weekly', test_date)
    assert expiry.weekday() == 3
    assert expiry > test_date

# ==================== Market Timing Tests ====================
def test_market_hours():
    """Test market open/close detection"""
    # Mock market open time
    with patch('datetime.datetime') as mock_datetime:
        mock_datetime.now.return_value = datetime.datetime(2024, 1, 1, 10, 0)
        assert is_market_open()
        
        # Mock market closed time
        mock_datetime.now.return_value = datetime.datetime(2024, 1, 1, 16, 0)
        assert not is_market_open()

# ==================== Position Management Tests ====================
def test_active_position_check(mock_strategy):
    """Test existing position detection"""
    # Setup
    mock_strategy.position_manager.positions = {
        'net': [{
            'expiry': '2024-01-25',
            'strike': 21500,
            'instrument_type': 'CE'
        }]
    }
    
    # Execute
    result = mock_strategy.position_manager.existing_position_check(
        '2024-01-25', 21500, 'CE'
    )
    
    # Verify
    assert result is True

# ==================== New Critical Test Cases ====================
def test_hedge_placement_below_threshold(mock_strategy):
    """Test hedge doesn't trigger below loss threshold"""
    # Setup (20% loss when threshold is 25%)
    mock_position = Mock(
        quantity=-1,
        average_price=100,
        last_price=80,
        instrument_type='CE'
    )
    mock_strategy.position_manager.positions = {'net': [mock_position]}
    config.HEDGE_LOSS_THRESHOLD = 0.25
    
    # Execute
    mock_strategy.manage_hedges()
    
    # Verify
    mock_strategy.order_manager.place_order.assert_not_called()

def test_concurrent_order_prevention(mock_strategy):
    """Test new orders blocked when existing orders are open"""
    # Setup
    mock_strategy.position_manager.orders = [{'status': 'OPEN'}]
    
    # Execute
    mock_strategy.manage_strategy()
    
    # Verify
    mock_strategy.order_manager.place_order.assert_not_called()

# ==================== Instrument Handling Tests ====================
def test_instrument_loading():
    """Test instrument loading and caching"""
    with patch('kiteconnect.KiteConnect.instruments') as mock_api:
        mock_api.return_value = [{
            'tradingsymbol': 'NIFTY25JAN21500CE',
            'segment': 'NFO-OPT',
            'strike': 21500,
            'expiry': '2024-01-25'
        }]
        im = InstrumentManager()
        assert len(im.nifty_instruments) > 0

# ==================== Order Management Tests ====================
def test_order_retry_mechanism():
    """Test order retry with exponential backoff"""
    order_mgr = OrderManager()
    with patch.object(order_mgr.kite, 'place_order', side_effect=Exception("API Error")):
        with pytest.raises(Exception):
            order_mgr.place_order('BUY', {}, 100, 'MARKET')
        assert order_mgr.kite.place_order.call_count == 3  # Initial + 2 retries

# ==================== Configuration Tests ====================
def test_config_defaults():
    """Verify critical config defaults"""
    assert config.LOT_SIZE == 75
    assert config.POINT_VALUE == 75
    assert config.STRADDLE_FLAG is True

# ==================== Full Strategy Lifecycle Test ====================
def test_full_strategy_lifecycle(mock_strategy):
    """Test complete strategy execution path"""
    # Setup market open conditions
    with patch('utils.is_market_open', return_value=True):
        # Setup positions
        mock_strategy.position_manager.calculate_unrealized_pnl.return_value = 5000
        mock_strategy.position_manager.get_active_positions.return_value = []
        
        # Setup instruments
        mock_strategy.instrument_manager.nifty_instruments = [
            {'tradingsymbol': 'NIFTY25JAN21500CE', 'strike': 21500, 'expiry': '2024-01-25', 'instrument_type': 'CE'},
            {'tradingsymbol': 'NIFTY25JAN21500PE', 'strike': 21500, 'expiry': '2024-01-25', 'instrument_type': 'PE'}
        ]
        
        # Execute
        mock_strategy.manage_strategy()
        
        # Verify
        assert mock_strategy.manage_straddle.called
        assert mock_strategy.manage_hedges.called
        assert mock_strategy.manage_profit_booking.called
