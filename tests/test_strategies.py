import os
import sys
import unittest
import datetime
import pandas as pd
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import modules
from core.strategy import Strategy
from core.order_manager import OrderManager
from core.expiry_manager import ExpiryManager
from core.risk_manager import RiskManager
from core.streaming import StreamingService
from utils.logger import Logger
from utils.notification import NotificationManager
from config import Config

class TestStrategies(unittest.TestCase):
    """Test cases for the short straddle/strangle strategy implementation"""
    
    def setUp(self):
        """Set up test environment before each test"""
        # Mock configuration
        self.config = Config()
        self.config.straddle = True
        self.config.strangle = False
        self.config.bias = 0
        self.config.lot_size = 50
        self.config.profit_percentage = 25
        self.config.stop_loss_percentage = 90
        self.config.profit_points = 250
        self.config.shutdown_loss = 12.5
        self.config.buy_hedge = True
        self.config.hedge_one_lot = True
        self.config.far_sell_add = True
        self.config.strangle_distance = 1000
        self.config.adjacency_gap = 200
        self.config.trend = "sideways"
        self.config.trend_distance = 2000
        self.config.strategy_conversion_threshold = 5
        self.config.tags = {
            "straddle_ce": "short_straddle_ce",
            "straddle_pe": "short_straddle_pe",
            "strangle_ce": "short_strangle_ce",
            "strangle_pe": "short_strangle_pe",
            "hedge_ce": "hedge_buy_ce",
            "hedge_pe": "hedge_buy_pe",
            "trend_ce": "trend_ce",
            "trend_pe": "trend_pe",
            "stop_loss": "stop_loss",
            "additional_sell": "additional_sell",
            "hedge_loss_sell": "hedge_loss_sell",
            "close_position": "close_position",
            "replacement_hedge": "replacement_hedge",
            "far_month_hedge": "far_month_hedge"
        }
        
        # Mock logger
        self.logger = MagicMock()
        self.logger.info = MagicMock()
        self.logger.error = MagicMock()
        self.logger.warning = MagicMock()
        
        # Mock Kite
        self.kite = MagicMock()
        
        # Mock order manager
        self.order_manager = MagicMock(spec=OrderManager)
        self.order_manager.get_instrument_token.return_value = 12345
        self.order_manager.get_ltp.return_value = 100
        self.order_manager.place_order.return_value = "order123"
        self.order_manager.refresh_positions.return_value = {"net": []}
        self.order_manager.refresh_orders.return_value = []
        self.order_manager.positions = {"net": []}
        self.order_manager.orders = {}
        self.order_manager.instruments_cache = {}
        
        # Mock expiry manager
        self.expiry_manager = MagicMock(spec=ExpiryManager)
        self.expiry_manager.get_far_month_expiry.return_value = datetime.datetime.now() + datetime.timedelta(days=90)
        self.expiry_manager.get_next_weekly_expiry.return_value = datetime.datetime.now() + datetime.timedelta(days=7)
        self.expiry_manager.is_expiry_day.return_value = False
        
        # Mock risk manager
        self.risk_manager = MagicMock(spec=RiskManager)
        self.risk_manager.is_trading_allowed.return_value = True
        self.risk_manager.check_shutdown_condition.return_value = False
        self.risk_manager.check_profit_exit_condition.return_value = False
        self.risk_manager.calculate_position_profit_percentage.return_value = 0
        self.risk_manager.check_position_loss_threshold.return_value = False
        
        # Mock streaming service
        self.streaming_service = MagicMock(spec=StreamingService)
        
        # Create strategy instance
        self.strategy = Strategy(
            self.kite,
            self.logger,
            self.config,
            self.order_manager,
            self.expiry_manager,
            self.risk_manager,
            self.streaming_service
        )
        
        # Mock spot price
        self.strategy.nifty_spot_price = 18000
    
    def test_update_spot_price(self):
        """Test updating spot price"""
        self.kite.ltp.return_value = {"NSE:NIFTY 50": {"last_price": 18000}}
        result = self.strategy.update_spot_price()
        self.assertEqual(result, 18000)
        self.assertEqual(self.strategy.nifty_spot_price, 18000)
    
    def test_get_atm_strike(self):
        """Test getting ATM strike price"""
        self.strategy.nifty_spot_price = 18025
        self.config.bias = 0
        result = self.strategy.get_atm_strike()
        self.assertEqual(result, 18000)  # Rounded to nearest 50
        
        self.strategy.nifty_spot_price = 18025
        self.config.bias = 25
        result = self.strategy.get_atm_strike()
        self.assertEqual(result, 18050)  # With bias
    
    def test_execute_short_straddle(self):
        """Test executing short straddle strategy"""
        # Mock that no straddle exists
        self.strategy._short_straddle_exists = MagicMock(return_value=False)
        self.strategy._place_short_straddle_orders = MagicMock()
        
        # Execute strategy
        self.strategy._execute_short_straddle()
        
        # Verify calls
        self.expiry_manager.get_far_month_expiry.assert_called_once()
        self.strategy._short_straddle_exists.assert_called_once()
        self.strategy._place_short_straddle_orders.assert_called_once()
    
    def test_execute_short_strangle(self):
        """Test executing short strangle strategy"""
        # Set strangle config
        self.config.straddle = False
        self.config.strangle = True
        
        # Mock that no strangle exists
        self.strategy._short_strangle_exists = MagicMock(return_value=False)
        self.strategy._place_short_strangle_orders = MagicMock()
        
        # Execute strategy
        self.strategy._execute_short_strangle()
        
        # Verify calls
        self.expiry_manager.get_far_month_expiry.assert_called_once()
        self.strategy._short_strangle_exists.assert_called_once()
        self.strategy._place_short_strangle_orders.assert_called_once()
    
    def test_short_straddle_exists(self):
        """Test checking if short straddle exists"""
        # Mock positions
        expiry = datetime.datetime.now() + datetime.timedelta(days=90)
        expiry_str = expiry.strftime('%y%b').upper()
        
        # No positions
        self.order_manager.positions = {"net": []}
        result = self.strategy._short_straddle_exists(expiry)
        self.assertFalse(result)
        
        # Only CE short position
        self.order_manager.positions = {"net": [
            {"tradingsymbol": f"NIFTY{expiry_str}18000CE", "quantity": -50}
        ]}
        result = self.strategy._short_straddle_exists(expiry)
        self.assertFalse(result)
        
        # Both CE and PE short positions
        self.order_manager.positions = {"net": [
            {"tradingsymbol": f"NIFTY{expiry_str}18000CE", "quantity": -50},
            {"tradingsymbol": f"NIFTY{expiry_str}18000PE", "quantity": -50}
        ]}
        result = self.strategy._short_straddle_exists(expiry)
        self.assertTrue(result)
    
    def test_place_short_straddle_orders(self):
        """Test placing short straddle orders"""
        expiry = datetime.datetime.now() + datetime.timedelta(days=90)
        strike = 18000
        
        # Mock methods
        self.strategy._buy_order_exists_at_strike = MagicMock(return_value=False)
        self.strategy._place_hedge_buy_orders = MagicMock()
        
        # Execute
        self.strategy._place_short_straddle_orders(expiry, strike)
        
        # Verify calls
        self.order_manager.get_instrument_token.assert_any_call(expiry, strike, "CE")
        self.order_manager.get_instrument_token.assert_any_call(expiry, strike, "PE")
        self.order_manager.place_order.assert_any_call(
            instrument_token=12345,
            transaction_type="SELL",
            quantity=self.config.lot_size,
            order_type="MARKET",
            tag="short_straddle_ce"
        )
        self.order_manager.place_order.assert_any_call(
            instrument_token=12345,
            transaction_type="SELL",
            quantity=self.config.lot_size,
            order_type="MARKET",
            tag="short_straddle_pe"
        )
        self.strategy._place_hedge_buy_orders.assert_called_once()
    
    def test_place_short_strangle_orders(self):
        """Test placing short strangle orders"""
        expiry = datetime.datetime.now() + datetime.timedelta(days=90)
        ce_strike = 19000
        pe_strike = 17000
        
        # Mock methods
        self.strategy._buy_order_exists_at_strike = MagicMock(return_value=False)
        self.strategy._place_hedge_buy_orders = MagicMock()
        
        # Execute
        self.strategy._place_short_strangle_orders(expiry, ce_strike, pe_strike)
        
        # Verify calls
        self.order_manager.get_instrument_token.assert_any_call(expiry, ce_strike, "CE")
        self.order_manager.get_instrument_token.assert_any_call(expiry, pe_strike, "PE")
        self.order_manager.place_order.assert_any_call(
            instrument_token=12345,
            transaction_type="SELL",
            quantity=self.config.lot_size,
            order_type="MARKET",
            tag="short_strangle_ce"
        )
        self.order_manager.place_order.assert_any_call(
            instrument_token=12345,
            transaction_type="SELL",
            quantity=self.config.lot_size,
            order_type="MARKET",
            tag="short_strangle_pe"
        )
        self.strategy._place_hedge_buy_orders.assert_called_once()
    
    def test_place_hedge_buy_orders(self):
        """Test placing hedge buy orders"""
        ce_token = 12345
        pe_token = 67890
        
        # Mock methods
        self.strategy._calculate_hedge_quantity = MagicMock(return_value=50)
        
        # Mock instruments cache
        self.order_manager.instruments_cache = {
            "key1": {"instrument_token": ce_token, "strike": 18000, "instrument_type": "CE"},
            "key2": {"instrument_token": pe_token, "strike": 18000, "instrument_type": "PE"}
        }
        
        # Execute
        self.strategy._place_hedge_buy_orders(ce_token, pe_token)
        
        # Verify calls
        self.order_manager.get_ltp.assert_any_call(ce_token)
        self.order_manager.get_ltp.assert_any_call(pe_token)
        self.order_manager.get_instrument_token.assert_any_call(
            self.expiry_manager.get_next_weekly_expiry(), 18100, "CE"
        )
        self.order_manager.get_instrument_token.assert_any_call(
            self.expiry_manager.get_next_weekly_expiry(), 17900, "PE"
        )
        self.order_manager.place_order.assert_any_call(
            instrument_token=12345,
            transaction_type="BUY",
            quantity=self.config.lot_size,
            order_type="MARKET",
            tag="hedge_buy_ce"
        )
        self.order_manager.place_order.assert_any_call(
            instrument_token=12345,
            transaction_type="BUY",
            quantity=self.config.lot_size,
            order_type="MARKET",
            tag="hedge_buy_pe"
        )
    
    def test_manage_profitable_legs(self):
        """Test managing profitable legs"""
        # Mock positions with one profitable position
        self.order_manager.positions = {"net": [
            {"tradingsymbol": "NIFTY25APR18000CE", "quantity": -50, "sell_price": 100, "instrument_token": 12345}
        ]}
        
        # Mock profit calculation
        self.risk_manager.calculate_position_profit_percentage.return_value = 30  # 30% profit
        
        # Mock methods
        self.strategy._add_stop_loss_for_position = MagicMock()
        self.strategy._add_new_sell_order_for_profitable_leg = MagicMock()
        
        # Execute
        self.strategy._manage_profitable_legs()
        
        # Verify calls
        self.risk_manager.calculate_position_profit_percentage.assert_called_once()
        self.strategy._add_stop_loss_for_position.assert_called_once()
        self.strategy._add_new_sell_order_for_profitable_leg.assert_called_once()
    
    def test_add_stop_loss_for_position(self):
        """Test adding stop loss for a profitable position"""
        position = {
            "tradingsymbol": "NIFTY25APR18000CE", 
            "quantity": -50, 
            "sell_price": 100, 
            "instrument_token": 12345
        }
        
        # Mock that no stop loss exists
        self.order_manager.get_orders_for_instrument.return_value = []
        
        # Execute
        self.strategy._add_stop_loss_for_position(position)
        
        # Verify calls
        self.order_manager.get_orders_for_instrument.assert_called_once_with(12345)
        self.order_manager.place_order.assert_called_once_with(
            instrument_token=12345,
            transaction_type="BUY",
            quantity=50,
            order_type="SL-M",
            trigger_price=90,  # 90% of sell price
            tag="stop_loss"
        )
    
    def test_close_orphan_hedge_orders(self):
        """Test closing orphan hedge orders"""
        # Mock positions with only buy orders for CE
        self.order_manager.positions = {"net": [
            {"tradingsymbol": "NIFTY25APR18000CE", "quantity": 50, "instrument_token": 12345}
        ]}
        
        # Mock method
        self.strategy._close_all_buy_positions_by_type = MagicMock()
        
        # Execute
        self.strategy._close_orphan_hedge_orders()
        
        # Verify calls
        self.strategy._close_all_buy_positions_by_type.assert_called_once_with("CE")
    
    def test_handle_expiry_day(self):
        """Test handling expiry day operations"""
        # Mock that today is an expiry day
        self.expiry_manager.is_expiry_day.return_value = True
        
        # Mock positions with expiring buy positions
        today = datetime.datetime.now().date()
        self.order_manager.positions = {"net": [
            {"tradingsymbol": "NIFTY25APR18000CE", "quantity": 50, "instrument_token": 12345}
        ]}
        
        # Mock instruments cache
        self.order_manager.instruments_cache = {
            "key1": {
                "instrument_token": 12345, 
                "strike": 18000, 
                "instrument_type": "CE",
                "expiry": datetime.datetime.combine(today, datetime.time())
            }
        }
        
        # Mock method
        self.strategy._replace_expiring_buy_positions = MagicMock()
        
        # Execute
        self.strategy._handle_expiry_day()
        
        # Verify calls
        self.strategy._replace_expiring_buy_positions.assert_called_once_with("CE", [
            {"tradingsymbol": "NIFTY25APR18000CE", "quantity": 50, "instrument_token": 12345}
        ])
    
    def test_execute_strategy(self):
        """Test executing the complete strategy"""
        # Mock methods
        self.strategy.update_spot_price = MagicMock(return_value=18000)
        self.strategy._execute_short_straddle = MagicMock()
        self.strategy._manage_profitable_legs = MagicMock()
        self.strategy._manage_hedge_buy_orders = MagicMock()
        self.strategy._close_orphan_hedge_orders = MagicMock()
        self.strategy._check_spot_price_touches_hedge = MagicMock()
        
        # Execute
        result = self.strategy.execute()
        
        # Verify calls
        self.risk_manager.is_trading_allowed.assert_called_once()
        self.risk_manager.check_shutdown_condition.assert_called_once()
        self.strategy.update_spot_price.assert_called_once()
        self.order_manager.refresh_positions.assert_called_once()
        self.order_manager.refresh_orders.assert_called_once()
        self.expiry_manager.is_expiry_day.assert_called_once()
        self.risk_manager.check_profit_exit_condition.assert_any_call(None, "CE")
        self.risk_manager.check_profit_exit_condition.assert_any_call(None, "PE")
        self.strategy._execute_short_straddle.assert_called_once()
        self.strategy._manage_profitable_legs.assert_called_once()
        self.strategy._manage_hedge_buy_orders.assert_called_once()
        self.strategy._close_orphan_hedge_orders.assert_called_once()
        self.strategy._check_spot_price_touches_hedge.assert_called_once()
        self.assertTrue(result)
    
    def test_shutdown_condition(self):
        """Test shutdown condition handling"""
        # Mock shutdown condition
        self.risk_manager.check_shutdown_condition.return_value = True
        
        # Mock method
        self.strategy._exit_all_positions = MagicMock()
        
        # Execute
        result = self.strategy.execute()
        
        # Verify calls
        self.risk_manager.check_shutdown_condition.assert_called_once()
        self.strategy._exit_all_positions.assert_called_once()
        self.assertFalse(result)
    
    def test_profit_exit_condition(self):
        """Test profit exit condition handling"""
        # Mock profit exit condition for CE
        self.risk_manager.check_profit_exit_condition.side_effect = [True, False]
        
        # Mock method
        self.strategy._exit_all_positions_by_type = MagicMock()
        
        # Execute
        self.strategy.execute()
        
        # Verify calls
        self.risk_manager.check_profit_exit_condition.assert_any_call(None, "CE")
        self.risk_manager.check_profit_exit_condition.assert_any_call(None, "PE")
        self.strategy._exit_all_positions_by_type.assert_called_once_with("CE")
    
    def test_add_new_sell_order_for_profitable_leg(self):
        """Test adding new sell order for a profitable leg"""
        position = {
            "tradingsymbol": "NIFTY25APR18000CE", 
            "quantity": -50, 
            "sell_price": 100, 
            "instrument_token": 12345
        }
        
        # Mock instruments cache
        self.order_manager.instruments_cache = {
            "key1": {
                "instrument_token": 12345, 
                "strike": 18000, 
                "instrument_type": "CE",
                "expiry": datetime.datetime.now() + datetime.timedelta(days=90)
            }
        }
        
        # Mock methods
        self.strategy._buy_order_exists_at_strike = MagicMock(return_value=False)
        self.strategy._place_single_hedge_buy_order = MagicMock()
        
        # Execute
        self.strategy._add_new_sell_order_for_profitable_leg(position)
        
        # Verify calls
        self.order_manager.get_instrument_token.assert_called_once()
        self.order_manager.place_order.assert_called_once()
        self.strategy._place_single_hedge_buy_order.assert_called_once()
    
    def test_add_sell_order_for_hedge_in_loss(self):
        """Test adding sell order for hedge in loss"""
        position = {
            "tradingsymbol": "NIFTY25APR18000CE", 
            "quantity": 50, 
            "buy_price": 100, 
            "instrument_token": 12345
        }
        
        # Mock instruments cache
        self.order_manager.instruments_cache = {
            "key1": {
                "instrument_token": 12345, 
                "strike": 18000, 
                "instrument_type": "CE",
                "expiry": datetime.datetime.now() + datetime.timedelta(days=7)
            }
        }
        
        # Mock methods
        self.strategy._buy_order_exists_at_strike = MagicMock(return_value=False)
        
        # Execute
        self.strategy._add_sell_order_for_hedge_in_loss(position)
        
        # Verify calls
        self.order_manager.get_instrument_token.assert_called_once()
        self.order_manager.place_order.assert_called_once_with(
            instrument_token=12345,
            transaction_type="SELL",
            quantity=self.config.lot_size,
            order_type="MARKET",
            tag="hedge_loss_sell"
        )
    
    def test_check_spot_price_touches_hedge(self):
        """Test checking if spot price touches hedge strike"""
        # Mock spot price
        self.strategy.nifty_spot_price = 18000
        
        # Mock positions with buy position at strike near spot
        self.order_manager.positions = {"net": [
            {"tradingsymbol": "NIFTY25APR18000CE", "quantity": 50, "instrument_token": 12345}
        ]}
        
        # Mock instruments cache
        self.order_manager.instruments_cache = {
            "key1": {
                "instrument_token": 12345, 
                "strike": 18000, 
                "instrument_type": "CE",
                "expiry": datetime.datetime.now() + datetime.timedelta(days=7)
            }
        }
        
        # Mock methods
        self.strategy._close_position = MagicMock()
        self.strategy._add_far_month_buy_order = MagicMock()
        
        # Execute
        self.strategy._check_spot_price_touches_hedge()
        
        # Verify calls
        self.strategy._close_position.assert_called_once()
        self.strategy._add_far_month_buy_order.assert_called_once()
    
    def test_add_far_month_buy_order(self):
        """Test adding far month buy order"""
        position = {
            "tradingsymbol": "NIFTY25APR18000CE", 
            "quantity": 50, 
            "buy_price": 100, 
            "instrument_token": 12345
        }
        
        # Mock instruments cache
        self.order_manager.instruments_cache = {
            "key1": {
                "instrument_token": 12345, 
                "strike": 18000, 
                "instrument_type": "CE",
                "expiry": datetime.datetime.now() + datetime.timedelta(days=7)
            }
        }
        
        # Mock methods
        self.strategy._find_strike_for_premium = MagicMock(return_value=18500)
        
        # Execute
        self.strategy._add_far_month_buy_order(position)
        
        # Verify calls
        self.expiry_manager.get_far_month_expiry.assert_called_once()
        self.order_manager.get_ltp.assert_called_once()
        self.strategy._find_strike_for_premium.assert_called_once()
        self.order_manager.get_instrument_token.assert_called_once()
        self.order_manager.place_order.assert_called_once_with(
            instrument_token=12345,
            transaction_type="BUY",
            quantity=100,  # 2x the original quantity
            order_type="MARKET",
            tag="far_month_hedge_replacement"
        )
    
    def test_find_strike_for_premium(self):
        """Test finding strike for target premium"""
        expiry = datetime.datetime.now() + datetime.timedelta(days=90)
        option_type = "CE"
        target_premium = 50
        
        # Mock get_atm_strike
        self.strategy.get_atm_strike = MagicMock(return_value=18000)
        
        # Mock get_instrument_token and get_ltp
        self.order_manager.get_instrument_token.side_effect = lambda exp, strike, opt: 12345 if strike == 18200 else None
        self.order_manager.get_ltp.side_effect = lambda token: 50 if token == 12345 else None
        
        # Execute
        result = self.strategy._find_strike_for_premium(expiry, option_type, target_premium)
        
        # Verify
        self.assertEqual(result, 18200)
    
    def test_close_position(self):
        """Test closing a position"""
        # Test closing a buy position
        position = {
            "tradingsymbol": "NIFTY25APR18000CE", 
            "quantity": 50, 
            "buy_price": 100, 
            "instrument_token": 12345
        }
        
        # Execute
        self.strategy._close_position(position)
        
        # Verify
        self.order_manager.place_order.assert_called_once_with(
            instrument_token=12345,
            transaction_type="SELL",
            quantity=50,
            order_type="MARKET",
            tag="close_position"
        )
        
        # Reset mock
        self.order_manager.place_order.reset_mock()
        
        # Test closing a sell position
        position = {
            "tradingsymbol": "NIFTY25APR18000CE", 
            "quantity": -50, 
            "sell_price": 100, 
            "instrument_token": 12345
        }
        
        # Execute
        self.strategy._close_position(position)
        
        # Verify
        self.order_manager.place_order.assert_called_once_with(
            instrument_token=12345,
            transaction_type="BUY",
            quantity=50,
            order_type="MARKET",
            tag="close_position"
        )
    
    def test_exit_all_positions(self):
        """Test exiting all positions"""
        # Mock positions
        self.order_manager.positions = {"net": [
            {"tradingsymbol": "NIFTY25APR18000CE", "quantity": 50, "instrument_token": 12345},
            {"tradingsymbol": "NIFTY25APR18000PE", "quantity": -50, "instrument_token": 67890},
            {"tradingsymbol": "NIFTY25APR19000CE", "quantity": 0, "instrument_token": 54321}  # Should be skipped
        ]}
        
        # Mock method
        self.strategy._close_position = MagicMock()
        
        # Execute
        self.strategy._exit_all_positions()
        
        # Verify
        self.assertEqual(self.strategy._close_position.call_count, 2)
    
    def test_exit_all_positions_by_type(self):
        """Test exiting all positions by type"""
        # Mock positions
        self.order_manager.positions = {"net": [
            {"tradingsymbol": "NIFTY25APR18000CE", "quantity": 50, "instrument_token": 12345},
            {"tradingsymbol": "NIFTY25APR18000PE", "quantity": -50, "instrument_token": 67890},
            {"tradingsymbol": "NIFTY25APR19000CE", "quantity": -25, "instrument_token": 54321}
        ]}
        
        # Mock method
        self.strategy._close_position = MagicMock()
        
        # Execute
        self.strategy._exit_all_positions_by_type("CE")
        
        # Verify
        self.assertEqual(self.strategy._close_position.call_count, 2)
    
    def test_close_all_buy_positions_by_type(self):
        """Test closing all buy positions by type"""
        # Mock positions
        self.order_manager.positions = {"net": [
            {"tradingsymbol": "NIFTY25APR18000CE", "quantity": 50, "instrument_token": 12345},
            {"tradingsymbol": "NIFTY25APR18000PE", "quantity": 50, "instrument_token": 67890},
            {"tradingsymbol": "NIFTY25APR19000CE", "quantity": -25, "instrument_token": 54321}
        ]}
        
        # Mock method
        self.strategy._close_position = MagicMock()
        
        # Execute
        self.strategy._close_all_buy_positions_by_type("CE")
        
        # Verify
        self.assertEqual(self.strategy._close_position.call_count, 1)
    
    def test_replace_expiring_buy_positions(self):
        """Test replacing expiring buy positions"""
        # Mock positions
        positions = [
            {"tradingsymbol": "NIFTY25APR18000CE", "quantity": 50, "instrument_token": 12345}
        ]
        
        # Mock sell positions
        self.order_manager.positions = {"net": [
            {"tradingsymbol": "NIFTY25MAY18000CE", "quantity": -100, "instrument_token": 67890, "strike": 18000}
        ]}
        
        # Mock methods
        self.strategy._close_position = MagicMock()
        
        # Execute
        self.strategy._replace_expiring_buy_positions("CE", positions)
        
        # Verify
        self.strategy._close_position.assert_called_once()
        self.expiry_manager.get_next_weekly_expiry.assert_called_once()
        self.order_manager.get_instrument_token.assert_called_once()
        self.order_manager.place_order.assert_called_once()
    
    def test_buy_order_exists_at_strike(self):
        """Test checking if buy order exists at strike"""
        # Mock positions
        self.order_manager.positions = {"net": [
            {"tradingsymbol": "NIFTY25APR18000CE", "quantity": 50, "instrument_token": 12345}
        ]}
        
        # Mock instruments cache
        expiry = datetime.datetime.now() + datetime.timedelta(days=7)
        self.order_manager.instruments_cache = {
            "key1": {
                "instrument_token": 12345, 
                "strike": 18000, 
                "instrument_type": "CE",
                "expiry": expiry
            }
        }
        
        # Execute - should find the buy order
        result = self.strategy._buy_order_exists_at_strike(expiry, 18000, "CE")
        self.assertTrue(result)
        
        # Execute - should not find buy order at different strike
        result = self.strategy._buy_order_exists_at_strike(expiry, 18050, "CE")
        self.assertFalse(result)
        
        # Execute - should not find buy order for different option type
        result = self.strategy._buy_order_exists_at_strike(expiry, 18000, "PE")
        self.assertFalse(result)
    
    def test_adjust_strike_for_conflict(self):
        """Test adjusting strike for conflict"""
        # Test positive adjustment
        result = self.strategy._adjust_strike_for_conflict(18000, 50)
        self.assertEqual(result, 18050)
        
        # Test negative adjustment
        result = self.strategy._adjust_strike_for_conflict(18000, -50)
        self.assertEqual(result, 17950)

    def test_execute_trend_based_strategy_sideways(self):
         """Test executing trend-based strategy with sideways trend"""
         # Set sideways trend
         self.config.trend = "sideways"
         
         # Mock methods
         self.strategy._execute_short_straddle = MagicMock()
         self.strategy._execute_short_strangle = MagicMock()
         
         # Execute
         self.strategy._execute_trend_based_strategy()
         
         # Verify
         self.strategy._execute_short_straddle.assert_called_once()
         self.strategy._execute_short_strangle.assert_not_called()
     
    def test_execute_trend_based_strategy_bullish(self):
         """Test executing trend-based strategy with bullish trend"""
         # Set bullish trend
         self.config.trend = "bullish"
         
         # Mock methods
         self.strategy._execute_trend_based_orders = MagicMock()
         
         # Execute
         self.strategy._execute_trend_based_strategy()
         
         # Verify
         self.strategy._execute_trend_based_orders.assert_called_once()
         args = self.strategy._execute_trend_based_orders.call_args[0]
         self.assertEqual(args[2], "bullish")
     
    def test_execute_trend_based_strategy_bearish(self):
         """Test executing trend-based strategy with bearish trend"""
         # Set bearish trend
         self.config.trend = "bearish"
         
         # Mock methods
         self.strategy._execute_trend_based_orders = MagicMock()
         
         # Execute
         self.strategy._execute_trend_based_strategy()
         
         # Verify
         self.strategy._execute_trend_based_orders.assert_called_once()
         args = self.strategy._execute_trend_based_orders.call_args[0]
         self.assertEqual(args[2], "bearish")
    
    def test_place_trend_order(self):
         """Test placing trend order"""
         expiry = datetime.datetime.now() + datetime.timedelta(days=90)
         strike = 18000
         option_type = "CE"
         order_type = "normal"
         
         # Mock methods
         self.strategy._buy_order_exists_at_strike = MagicMock(return_value=False)
         self.strategy._place_single_hedge_buy_order = MagicMock()
         
         # Execute
         self.strategy._place_trend_order(expiry, strike, option_type, order_type)
         
         # Verify
         self.order_manager.get_instrument_token.assert_called_once()
         self.order_manager.place_order.assert_called_once()
         self.strategy._place_single_hedge_buy_order.assert_called_once()
    
    def test_check_strategy_conversion(self):
         """Test checking strategy conversion"""
         expiry = datetime.datetime.now() + datetime.timedelta(days=90)
         normal_type = "PE"
         far_type = "CE"
         
         # Mock positions with far order in profit
         self.order_manager.positions = {"net": [
             {
                 "tradingsymbol": "NIFTY25APR20000CE",
                 "quantity": -50,
                 "sell_price": 100,
                 "instrument_token": 12345
             }
         ]}
         
         # Mock instruments cache
         self.order_manager.instruments_cache = {
             "key1": {
                 "instrument_token": 12345,
                 "strike": 20000,
                 "instrument_type": "CE",
                 "expiry": expiry
             }
         }
         
         # Mock orders
         self.order_manager.orders = {
             "order123": {
                 "order_id": "order123",
                 "tag": self.config.tags["trend_ce"]
             }
         }
         
         # Mock LTP
         self.order_manager.get_ltp.return_value = 110  # 10% increase
         
         # Mock methods
         self.strategy._is_trend_order = MagicMock(return_value=True)
         self.strategy._close_position = MagicMock()
         self.strategy._close_hedge_for_position = MagicMock()
         self.strategy._place_trend_order = MagicMock()
         
         # Execute
         self.strategy._check_strategy_conversion(expiry, normal_type, far_type)
         
         # Verify
         self.strategy._is_trend_order.assert_called_once()
         self.strategy._close_position.assert_called_once()
         self.strategy._close_hedge_for_position.assert_called_once()
         self.strategy._place_trend_order.assert_called_once()
    
    def test_sell_order_exists_for_type(self):
         """Test checking if sell order exists for type"""
         expiry = datetime.datetime.now() + datetime.timedelta(days=90)
         option_type = "CE"
         
         # Mock positions with sell order
         self.order_manager.positions = {"net": [
             {
                 "tradingsymbol": "NIFTY25APR18000CE",
                 "quantity": -50,
                 "sell_price": 100,
                 "instrument_token": 12345
             }
         ]}
         
         # Mock instruments cache
         self.order_manager.instruments_cache = {
             "key1": {
                 "instrument_token": 12345,
                 "strike": 18000,
                 "instrument_type": "CE",
                 "expiry": expiry
             }
         }
         
         # Execute
         result = self.strategy._sell_order_exists_for_type(expiry, option_type)
         
         # Verify
         self.assertTrue(result)
         
         # Test with no matching sell order
         self.order_manager.positions = {"net": [
             {
                 "tradingsymbol": "NIFTY25APR18000PE",
                 "quantity": -50,
                 "sell_price": 100,
                 "instrument_token": 67890
             }
         ]}
         
         # Execute
         result = self.strategy._sell_order_exists_for_type(expiry, option_type)
         
         # Verify
         self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
