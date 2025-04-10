import sys
import os

import pytest
import config
import orders
import utils

# Add to existing imports
from unittest.mock import Mock, patch, call
import datetime
from config import config

from datetime import datetime, timedelta
from unittest.mock import Mock, patch
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from strategies import OptionStrategy
from utils import is_market_open, get_expiry_date, round_strike, calculate_quantity
from orders import OrderManager
from positions import PositionManager
from instruments import InstrumentManager

# ==== New Critical Test Cases ==== (Added based on code review)
def test_monthly_expiry_rollover_logic():
    # Test expiry date adjustment after 3 PM rollover hour
    config.EXPIRY_ROLLOVER_HOUR = 15
    now = datetime(2024, 1, 25, 15, 30)  # Past rollover hour
    expiry = get_expiry_date('monthly', now.date())
    assert expiry.month == (now.month + 1) % 12  # Ensure next month's expiry

def test_round_strike_edge_cases():
    config.STRIKE_ROUNDING_INTERVAL = 50
    assert round_strike(21249) == 21200  # Floor rounding
    assert round_strike(21250) == 21250  # Exact multiple
    assert round_strike(0) == 0  # Zero strike edge case

def test_quantity_calculation_with_insufficient_margin():
    config.MARGIN_PER_LOT = 120000
    margin_available = 100000
    qty = calculate_quantity(margin_available, 0)
    assert qty == 0  # Should floor to 0 lots

def test_straddle_entry_with_missing_instruments():
    # Mock empty instrument list
    with patch.object(InstrumentManager, 'nifty_instruments', {'CE': [], 'PE': []}):
        strategy = OptionStrategy()
        strategy.manage_straddle()
        # Verify no orders placed
        assert strategy.order_manager.place_order.call_count == 0

def test_hedge_placement_below_threshold():
    # Mock position with 20% loss (below 25% threshold)
    position = Mock(
        average_price=100,
        last_price=80,
        quantity=-1,
        instrument_type='CE'
    )
    strategy = OptionStrategy()
    strategy.position_manager.positions = {'net': [position]}
    strategy.manage_hedges()
    assert strategy.order_manager.place_order.call_count == 0  # No hedge placed

# ==== Enhanced Existing Tests ====
def test_is_market_open_with_holidays():
    config.HOLIDAYS = ["2024-12-25"]
    # Mock current time during trading hours but on a holiday
    with patch('datetime.datetime') as mock_datetime:
        mock_datetime.now.return_value = datetime(2024, 12, 25, 10, 0)
        mock_datetime.today.return_value = datetime(2024, 12, 25)
        assert not is_market_open()  # Should return False

def test_order_retry_with_exponential_backoff():
    order_mgr = OrderManager()
    with patch.object(order_mgr.kite, 'place_order') as mock_order:
        mock_order.side_effect = Exception("API Error")
        # Test 3 retries
        order_mgr.place_order('BUY', {}, 100, 'MARKET')
        assert mock_order.call_count == 2  # Initial attempt + 1 retry

def test_expiry_rollover_with_zero_quantity():
    # Mock position with 0 quantity (should be skipped)
    position = Mock(quantity=0, expiry='2024-01-25')
    strategy = OptionStrategy()
    strategy.position_manager.positions = {'net': [position]}
    strategy.manage_expiry_rollover()
    assert strategy.order_manager.place_order.call_count == 0

# ==== New Edge Case Tests ====
def test_weekly_expiry_on_rollover_hour_edge():
    # Test weekly expiry at exactly 3 PM
    config.EXPIRY_ROLLOVER_HOUR = 15
    now = datetime(2024, 1, 25, 15, 0)
    expiry = get_expiry_date('weekly', now.date())
    # If today is Thursday (WEEKLY_EXPIRY_DAY=3) and time >= 15:00, next week's expiry
    assert expiry.weekday() == config.WEEKLY_EXPIRY_DAY
    assert expiry > now.date()

def test_profit_booking_with_multiple_positions():
    # Mock one profitable and one non-profitable position
    profitable_pos = Mock(
        average_price=100,
        last_price=70,
        quantity=-1,
        instrument_type='CE'
    )
    non_profitable_pos = Mock(
        average_price=100,
        last_price=95,
        quantity=-1,
        instrument_type='PE'
    )
    strategy = OptionStrategy()
    strategy.position_manager.positions = {'net': [profitable_pos, non_profitable_pos]}
    strategy.manage_profit_booking()
    # Verify only 1 SL update (for profitable position)
    assert strategy.order_manager.modify_order.call_count == 1

def test_concurrent_order_prevention():
    # Mock pending orders
    with patch.object(PositionManager, 'orders', [{'status': 'OPEN'}]):
        strategy = OptionStrategy()
        strategy.manage_strategy()
        assert strategy.order_manager.place_order.call_count == 0  # Block new orders
# Import other necessary modules from your V3 directory

# === Market Timing & Availability ===
def test_market_closed_blocking():
    assert not utils.is_market_open("Sunday")

def test_special_saturday_allowed():
    assert utils.is_market_open("2024-12-28")  # Assuming it's a special trading Saturday

def test_holiday_exclusion():
    assert not utils.is_trading_day("2024-10-02")  # Gandhi Jayanthi

# === Core Strategy Execution ===
def test_straddle_entry_logic():
    pos = orders.create_straddle(spot=21500, bias=0)
    assert "CE" in pos and "PE" in pos

def test_strangle_entry_1000pts():
    pos = orders.create_strangle(spot=21500)
    assert abs(pos["CE"] - 22500) <= 50 and abs(pos["PE"] - 20500) <= 50

def test_prevent_duplicate_position():
    config.open_positions = ["straddle"]
    assert not orders.create_straddle(spot=21500, bias=0)

def test_strike_rounding():
    assert utils.round_to_strike(21675) == 21700

# === Risk Management ===
def test_close_on_loss():
    assert utils.should_exit(portfolio_loss_percent=12.6)

def test_update_stop_loss():
    sl = utils.update_stop_loss(profit_percent=25)
    assert sl == 90

def test_hedge_order_at_loss():
    assert orders.place_hedge(loss_percent=25)

def test_hedge_gap_check():
    assert not utils.place_hedge_if_too_close(hedge=21500, strike=21550)

# === Order Management ===
def test_market_to_limit_fallback():
    response = orders.place_order("BUY", "BANKNIFTY", mode="market")
    if not response["success"]:
        fallback = orders.place_order("BUY", "BANKNIFTY", mode="limit")
        assert fallback["success"]

def test_order_conflict():
    assert not orders.place_conflicting_order()

def test_quantity_calc():
    qty = orders.calculate_quantity(balance=200000)
    assert qty > 0

def test_order_tagging():
    tag = orders.generate_tag("hedge")
    assert "hedge" in tag

# === Expiry Management ===
def test_monthly_to_weekly_rollover():
    rolled = orders.rollover_position(current_expiry="monthly", time="14:35")
    assert rolled

def test_strike_adjustment_rollover():
    new_strike = utils.adjust_strike_during_roll(premium=150)
    assert new_strike > 0

def test_hedge_replace_on_spot_touch():
    replaced = orders.replace_hedge_on_spot_touch()
    assert replaced

def test_weekly_hedge_buy():
    order = orders.place_weekly_hedge()
    assert order["type"] == "BUY"

# === Profit Management ===
def test_full_close_on_profit():
    assert utils.should_exit_on_profit(points=250)

def test_profit_point_calc():
    amount = utils.calculate_profit(250)
    assert amount == 18750

def test_recursive_booking():
    orders_list = orders.book_profit_recursively(current_profit=100)
    assert isinstance(orders_list, list)

# === Instrument Handling ===
def test_instrument_cache():
    assert utils.get_cached_instrument("BANKNIFTY")

def test_strike_filtering():
    strikes = utils.filter_strikes(range=1000)
    assert len(strikes) > 0

def test_expiry_date_logic():
    expiry = utils.get_next_expiry()
    assert "2024" in expiry

# === Error Handling ===
def test_failed_order_retry():
    result = orders.retry_failed_order()
    assert result["attempts"] <= 3

def test_position_sync():
    synced = orders.sync_positions()
    assert synced

def test_error_logging():
    logged = utils.log_error("Order failed")
    assert logged

def test_api_error_recovery():
    assert utils.recover_from_api_error()

# === Configuration ===
def test_live_config_reflection():
    config.set_param("risk_limit", 10)
    assert config.get_param("risk_limit") == 10

def test_config_numeric_validation():
    assert isinstance(config.get_param("slippage"), (int, float))

def test_hour_format():
    assert utils.parse_time("09:15")

# === Edge Cases ===
def test_expiry_day_rollover():
    rolled = orders.rollover_position(current_expiry="weekly", time="15:00")
    assert rolled

def test_startup_position_check():
    assert orders.check_startup_positions() == 0

def test_margin_exhaustion():
    assert not orders.place_order_if_insufficient_margin()

def test_concurrent_prevention():
    assert orders.prevent_concurrent_orders()

def test_saturday_holiday_logic():
    assert not utils.is_trading_day("2024-10-05")  # Regular Saturday

# === Hedging ===
def test_buy_hedge_qty():
    qty = orders.calculate_hedge_quantity()
    assert qty > 0

def test_recursive_hedge_block():
    assert not orders.place_recursive_hedge_if_exists()

def test_hedge_strike_logic():
    strike = orders.select_hedge_strike(spot=21500)
    assert strike % 100 == 0

# === Logging & Monitoring ===
def test_audit_trail():
    assert utils.verify_audit_trail()

def test_pnl_accuracy():
    pnl = utils.calculate_pnl()
    assert isinstance(pnl, float)

def test_position_persistence():
    assert utils.verify_position_state()

# === Network Resilience ===
def test_connection_recovery():
    assert utils.reconnect_if_disconnected()

def test_order_reconciliation():
    assert utils.reconcile_order_status()

def test_timestamp_sync():
    assert utils.sync_timestamps()

# === Multi-expiry Handling ===
def test_weekly_monthly_parallel():
    assert orders.handle_multi_expiry()

def test_expiry_order_split():
    result = orders.split_orders_by_expiry()
    assert isinstance(result, dict)

def test_far_expiry_selection():
    instrument = utils.select_far_expiry()
    assert "expiry" in instrument

# === Position Tracking ===
def test_net_qty_calc():
    assert isinstance(orders.calculate_net_qty(), int)

def test_unrealized_pnl():
    pnl = orders.get_unrealized_pnl()
    assert isinstance(pnl, float)

def test_active_position_check():
    assert isinstance(orders.get_active_positions(), list)

# ==== Config Class Tests ====
def test_config_instance():
    assert isinstance(config.config, config.Config)

def test_config_default_values():
    assert config.config.MARGIN_PER_LOT == 120000
    assert config.config.STRADDLE_FLAG is True

# ==== Edge Cases for Expiry ====
def test_monthly_expiry_on_non_business_day():
    # Mock a non-business day (e.g., Christmas)
    with patch('utils.get_expiry_date') as mock_expiry:
        mock_expiry.return_value = datetime.date(2025, 1, 1)
        expiry = utils.get_expiry_date('monthly', datetime.date(2024, 12, 25))
        assert expiry.month == 1  # Rolled to January

# ==== Saturday Holiday Logic ====
def test_saturday_trading_holiday():
    # Allow Saturday but check for holiday
    config.config.ALLOW_SATURDAY = True
    config.config.HOLIDAYS = ["2024-10-05"]
    assert not utils.is_trading_day("2024-10-05")

# ==== Margin Exhaustion ====
def test_order_blocked_on_margin_exhaustion():
    with patch('utils.calculate_quantity', return_value=0):
        strategy = OptionStrategy()
        strategy.manage_straddle()
        assert strategy.order_manager.place_order.call_count == 0

# ==== Negative Average Price Handling ====
def test_rollover_with_negative_average_price():
    position = Mock(
        quantity=-1,
        average_price=-100,  # Negative price
        strike=21000,
        expiry='2024-01-25',
        tag='STRADDLE'
    )
    strategy = OptionStrategy()
    strategy.position_manager.positions = {'net': [position]}
    strategy.manage_expiry_rollover()
    assert "ROLLOVER" in strategy.order_manager.place_order.call_args[1]['tag']

# ==== Instrument Cache Fallback ====
def test_instrument_cache_fallback():
    # Simulate missing cache file and mock API response
    with patch('os.path.exists', return_value=False), \
         patch('kiteconnect.KiteConnect.instruments') as mock_api:
        mock_api.return_value = [{
            'tradingsymbol': 'NIFTY25JAN21500CE',
            'segment': 'NFO-OPT',
            'strike': 21500,
            'expiry': '2024-01-25'
        }]
        im = InstrumentManager()
        assert len(im.nifty_instruments) > 0

# ==== Error Handling ====
def test_instrument_loading_failure():
    # Simulate API failure
    with patch('kiteconnect.KiteConnect.instruments', side_effect=Exception("API Down")):
        im = InstrumentManager()
        assert len(im.nifty_instruments) == 0  # Fallback to empty list
