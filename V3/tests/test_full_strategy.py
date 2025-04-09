import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
import config
import orders
import utils
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
