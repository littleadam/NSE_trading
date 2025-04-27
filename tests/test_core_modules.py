import os
import sys
import unittest
from unittest.mock import MagicMock, patch
import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import modules
from core.order_manager import OrderManager
from core.expiry_manager import ExpiryManager
from core.risk_manager import RiskManager
from utils.logger import Logger
from config import Config

class TestOrderManager(unittest.TestCase):
    """Test cases for the OrderManager class"""
    
    def setUp(self):
        """Set up test environment before each test"""
        # Mock configuration
        self.config = Config()
        
        # Mock logger
        self.logger = MagicMock()
        self.logger.info = MagicMock()
        self.logger.error = MagicMock()
        self.logger.warning = MagicMock()
        
        # Mock Kite
        self.kite = MagicMock()
        
        # Sample instruments data
        self.sample_instruments = [
            {
                'instrument_token': 12345,
                'tradingsymbol': 'NIFTY25APR18000CE',
                'name': 'NIFTY',
                'expiry': datetime.datetime(2025, 4, 25),
                'strike': 18000,
                'instrument_type': 'CE',
                'exchange': 'NFO'
            },
            {
                'instrument_token': 67890,
                'tradingsymbol': 'NIFTY25APR18000PE',
                'name': 'NIFTY',
                'expiry': datetime.datetime(2025, 4, 25),
                'strike': 18000,
                'instrument_type': 'PE',
                'exchange': 'NFO'
            }
        ]
        
        # Mock kite.instruments
        self.kite.instruments.return_value = self.sample_instruments
        
        # Create OrderManager instance
        self.order_manager = OrderManager(self.kite, self.logger, self.config)
        
        # Override instruments_cache for testing
        self.order_manager.instruments_cache = {
            '2025-04-25_18000_CE': self.sample_instruments[0],
            '2025-04-25_18000_PE': self.sample_instruments[1]
        }
    
    def test_init_instruments_cache(self):
        """Test initializing instruments cache"""
        # Reset cache
        self.order_manager.instruments_cache = {}
        
        # Call method
        self.order_manager._init_instruments_cache()
        
        # Verify
        self.kite.instruments.assert_called_once_with("NFO")
        self.assertEqual(len(self.order_manager.instruments_cache), 2)
    
    def test_get_instrument(self):
        """Test getting instrument from cache"""
        # Get existing instrument
        expiry = datetime.datetime(2025, 4, 25)
        strike = 18000
        instrument_type = "CE"
        
        result = self.order_manager.get_instrument(expiry, strike, instrument_type)
        
        self.assertEqual(result['instrument_token'], 12345)
        self.assertEqual(result['tradingsymbol'], 'NIFTY25APR18000CE')
        
        # Get non-existent instrument
        result = self.order_manager.get_instrument(expiry, 19000, instrument_type)
        self.assertIsNone(result)
    
    def test_get_instrument_token(self):
        """Test getting instrument token"""
        # Get existing instrument token
        expiry = datetime.datetime(2025, 4, 25)
        strike = 18000
        instrument_type = "CE"
        
        result = self.order_manager.get_instrument_token(expiry, strike, instrument_type)
        
        self.assertEqual(result, 12345)
        
        # Get non-existent instrument token
        result = self.order_manager.get_instrument_token(expiry, 19000, instrument_type)
        self.assertIsNone(result)
    
    def test_refresh_positions(self):
        """Test refreshing positions"""
        # Mock kite.positions
        self.kite.positions.return_value = {
            'net': [
                {
                    'tradingsymbol': 'NIFTY25APR18000CE',
                    'instrument_token': 12345,
                    'quantity': -50,
                    'sell_price': 100,
                    'buy_price': 0
                }
            ]
        }
        
        # Call method
        result = self.order_manager.refresh_positions()
        
        # Verify
        self.kite.positions.assert_called_once()
        self.assertEqual(len(result['net']), 1)
        self.assertEqual(self.order_manager.positions, result)
    
    def test_refresh_orders(self):
        """Test refreshing orders"""
        # Mock kite.orders
        self.kite.orders.return_value = [
            {
                'order_id': 'order123',
                'tradingsymbol': 'NIFTY25APR18000CE',
                'instrument_token': 12345,
                'transaction_type': 'SELL',
                'quantity': 50,
                'status': 'COMPLETE'
            }
        ]
        
        # Call method
        result = self.order_manager.refresh_orders()
        
        # Verify
        self.kite.orders.assert_called_once()
        self.assertEqual(len(result), 1)
        self.assertEqual(len(self.order_manager.orders), 1)
        self.assertEqual(self.order_manager.orders['order123']['order_id'], 'order123')
    
    def test_place_order(self):
        """Test placing an order"""
        # Mock kite.place_order
        self.kite.place_order.return_value = 'order123'
        
        # Call method
        result = self.order_manager.place_order(
            instrument_token=12345,
            transaction_type="SELL",
            quantity=50,
            order_type="MARKET",
            tag="test_order"
        )
        
        # Verify
        self.kite.place_order.assert_called_once()
        self.assertEqual(result, 'order123')
        
        # Test market order failure and fallback to limit
        self.kite.place_order.reset_mock()
        self.kite.place_order.side_effect = [Exception("Market order failed"), 'order456']
        self.kite.ltp.return_value = {'12345': {'last_price': 100}}
        
        # Call method
        result = self.order_manager.place_order(
            instrument_token=12345,
            transaction_type="SELL",
            quantity=50,
            order_type="MARKET",
            tag="test_order"
        )
        
        # Verify fallback to limit order
        self.assertEqual(self.kite.place_order.call_count, 2)
        self.assertEqual(result, 'order456')
    
    def test_modify_order(self):
        """Test modifying an order"""
        # Mock kite.modify_order
        self.kite.modify_order.return_value = True
        
        # Call method
        result = self.order_manager.modify_order(
            order_id='order123',
            price=95,
            quantity=75
        )
        
        # Verify
        self.kite.modify_order.assert_called_once()
        self.assertTrue(result)
        
        # Test failure
        self.kite.modify_order.reset_mock()
        self.kite.modify_order.side_effect = Exception("Modify failed")
        
        # Call method
        result = self.order_manager.modify_order(
            order_id='order123',
            price=95
        )
        
        # Verify
        self.kite.modify_order.assert_called_once()
        self.assertFalse(result)
    
    def test_cancel_order(self):
        """Test cancelling an order"""
        # Mock kite.cancel_order
        self.kite.cancel_order.return_value = True
        
        # Call method
        result = self.order_manager.cancel_order('order123')
        
        # Verify
        self.kite.cancel_order.assert_called_once()
        self.assertTrue(result)
        
        # Test failure
        self.kite.cancel_order.reset_mock()
        self.kite.cancel_order.side_effect = Exception("Cancel failed")
        
        # Call method
        result = self.order_manager.cancel_order('order123')
        
        # Verify
        self.kite.cancel_order.assert_called_once()
        self.assertFalse(result)
    
    def test_get_order_status(self):
        """Test getting order status"""
        # Setup orders
        self.order_manager.orders = {
            'order123': {
                'order_id': 'order123',
                'status': 'COMPLETE'
            }
        }
        
        # Call method
        result = self.order_manager.get_order_status('order123')
        
        # Verify
        self.assertEqual(result, 'COMPLETE')
        
        # Test non-existent order
        result = self.order_manager.get_order_status('order456')
        self.assertIsNone(result)
    
    def test_is_order_complete(self):
        """Test checking if order is complete"""
        # Setup orders
        self.order_manager.orders = {
            'order123': {
                'order_id': 'order123',
                'status': 'COMPLETE'
            },
            'order456': {
                'order_id': 'order456',
                'status': 'PENDING'
            }
        }
        
        # Call method
        result1 = self.order_manager.is_order_complete('order123')
        result2 = self.order_manager.is_order_complete('order456')
        
        # Verify
        self.assertTrue(result1)
        self.assertFalse(result2)
    
    def test_get_ltp(self):
        """Test getting last traded price"""
        # Mock kite.ltp
        self.kite.ltp.return_value = {'12345': {'last_price': 100}}
        
        # Call method
        result = self.order_manager.get_ltp(12345)
        
        # Verify
        self.kite.ltp.assert_called_once_with([12345])
        self.assertEqual(result, 100)
        
        # Test failure
        self.kite.ltp.reset_mock()
        self.kite.ltp.side_effect = Exception("LTP failed")
        
        # Call method
        result = self.order_manager.get_ltp(12345)
        
        # Verify
        self.kite.ltp.assert_called_once_with([12345])
        self.assertIsNone(result)
    
    def test_get_margin_used(self):
        """Test getting margin used"""
        # Mock kite.margins
        self.kite.margins.return_value = {
            'equity': {
                'utilised': {
                    'debits': 50000
                }
            }
        }
        
        # Call method
        result = self.order_manager.get_margin_used()
        
        # Verify
        self.kite.margins.assert_called_once()
        self.assertEqual(result, 50000)
        
        # Test failure
        self.kite.margins.reset_mock()
        self.kite.margins.side_effect = Exception("Margins failed")
        
        # Call method
        result = self.order_manager.get_margin_used()
        
        # Verify
        self.kite.margins.assert_called_once()
        self.assertIsNone(result)
    
    def test_get_orders_for_instrument(self):
        """Test getting orders for an instrument"""
        # Setup orders
        self.order_manager.orders = {
            'order123': {
                'order_id': 'order123',
                'instrument_token': 12345,
                'status': 'COMPLETE'
            },
            'order456': {
                'order_id': 'order456',
                'instrument_token': 12345,
                'status': 'PENDING'
            },
            'order789': {
                'order_id': 'order789',
                'instrument_token': 67890,
                'status': 'COMPLETE'
            }
        }
        
        # Call method
        result = self.order_manager.get_orders_for_instrument(12345)
        
        # Verify
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['order_id'], 'order123')
        self.assertEqual(result[1]['order_id'], 'order456')

class TestExpiryManager(unittest.TestCase):
    """Test cases for the ExpiryManager class"""
    
    def setUp(self):
        """Set up test environment before each test"""
        # Mock configuration
        self.config = Config()
        
        # Mock logger
        self.logger = MagicMock()
        self.logger.info = MagicMock()
        self.logger.error = MagicMock()
        self.logger.warning = MagicMock()
        
        # Mock Kite
        self.kite = MagicMock()
        
        # Sample instruments data with expiry dates
        today = datetime.datetime.now().date()
        self.sample_instruments = [
            # Weekly expiries
            {
                'instrument_token': 11111,
                'tradingsymbol': 'NIFTY25APR18000CE',
                'name': 'NIFTY',
                'expiry': datetime.datetime.combine(today + datetime.timedelta(days=3), datetime.time()),
                'strike': 18000,
                'instrument_type': 'CE'
            },
            {
                'instrument_token': 22222,
                'tradingsymbol': 'NIFTY02MAY18000CE',
                'name': 'NIFTY',
                'expiry': datetime.datetime.combine(today + datetime.timedelta(days=10), datetime.time()),
                'strike': 18000,
                'instrument_type': 'CE'
            },
            # Monthly expiries
            {
                'instrument_token': 33333,
                'tradingsymbol': 'NIFTY30MAY18000CE',
                'name': 'NIFTY',
                'expiry': datetime.datetime.combine(today + datetime.timedelta(days=30), datetime.time()),
                'strike': 18000,
                'instrument_type': 'CE'
            },
            {
                'instrument_token': 44444,
                'tradingsymbol': 'NIFTY27JUN18000CE',
                'name': 'NIFTY',
                'expiry': datetime.datetime.combine(today + datetime.timedelta(days=60), datetime.time()),
                'strike': 18000,
                'instrument_type': 'CE'
            },
            {
                'instrument_token': 55555,
                'tradingsymbol': 'NIFTY25JUL18000CE',
                'name': 'NIFTY',
                'expiry': datetime.datetime.combine(today + datetime.timedelta(days=90), datetime.time()),
                'strike': 18000,
                'instrument_type': 'CE'
            }
        ]
        
        # Mock kite.instruments
        self.kite.instruments.return_value = self.sample_instruments
        
        # Create ExpiryManager instance
        self.expiry_manager = ExpiryManager(self.kite, self.logger, self.config)
        
        # Override expiry dates for testing
        self.expiry_manager.weekly_expiry_dates = [
            self.sample_instruments[0]['expiry'],
            self.sample_instruments[1]['expiry']
        ]
        self.expiry_manager.monthly_expiry_dates = [
            self.sample_instruments[2]['expiry'],
            self.sample_instruments[3]['expiry'],
            self.sample_instruments[4]['expiry']
        ]
    
    def test_get_far_month_expiry(self):
        """Test getting far month expiry"""
        # Call method
        result = self.expiry_manager.get_far_month_expiry()
        
        # Verify - should return the 3rd monthly expiry
        self.assertEqual(result, self.sample_instruments[4]['expiry'])
    
    def test_get_next_weekly_expiry(self):
        """Test getting next weekly expiry"""
        # Call method
        result = self.expiry_manager.get_next_weekly_expiry()
        
        # Verify - should return the 1st weekly expiry
        self.assertEqual(result, self.sample_instruments[0]['expiry'])
    
    def test_is_expiry_day(self):
        """Test checking if today is an expiry day"""
        # Mock today as not an expiry day
        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime.datetime(2025, 4, 21)  # Not an expiry day
            mock_datetime.combine = datetime.datetime.combine
            
            # Call method
            result = self.expiry_manager.is_expiry_day()
            
            # Verify
            self.assertFalse(result)
        
        # Mock today as an expiry day
        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime.datetime(2025, 4, 25)  # An expiry day
            mock_datetime.combine = datetime.datetime.combine
            
            # Override is_expiry_day for testing
            self.expiry_manager.is_expiry_day = lambda: True
            
            # Call method
            result = self.expiry_manager.is_expiry_day()
            
            # Verify
            self.assertTrue(result)
    
    def test_get_days_to_expiry(self):
        """Test getting days to expiry"""
        # Get days to a specific expiry
        today = datetime.datetime.now().date()
        expiry = datetime.datetime.combine(today + datetime.timedelta(days=10), datetime.time())
        
        # Call method
        result = self.expiry_manager.get_days_to_expiry(expiry)
        
        # Verify
        self.assertEqual(result, 10)
    
    def test_is_monthly_expiry(self):
        """Test checking if an expiry is a monthly expiry"""
        # Check a monthly expiry
        monthly_expiry = self.sample_instruments[2]['expiry']
        
        # Call method
        result = self.expiry_manager.is_monthly_expiry(monthly_expiry)
        
        # Verify
        self.assertTrue(result)
        
        # Check a weekly expiry
        weekly_expiry = self.sample_instruments[0]['expiry']
        
        # Call method
        result = self.expiry_manager.is_monthly_expiry(weekly_expiry)
        
        # Verify
        self.assertFalse(result)

class TestRiskManager(unittest.TestCase):
    """Test cases for the RiskManager class"""
    
    def setUp(self):
        """Set up test environment before each test"""
        # Mock configuration
        self.config = Config()
        self.config.capital_allocated = 500000
        self.config.shutdown_loss = 12.5
        self.config.profit_points = 250
        
        # Mock logger
        self.logger = MagicMock()
        self.logger.info = MagicMock()
        self.logger.error = MagicMock()
        self.logger.warning = MagicMock()
        
        # Mock Kite
        self.kite = MagicMock()
        
        # Mock OrderManager
        self.order_manager = MagicMock()
        self.order_manager.refresh_positions.return_value = {"net": []}
        self.order_manager.get_ltp.return_value = 100
        self.order_manager.get_margin_used.return_value = 100000
        
        # Create RiskManager instance
        self.risk_manager = RiskManager(self.kite, self.logger, self.config, self.order_manager)
    
    def test_check_shutdown_condition(self):
        """Test checking shutdown condition"""
        # Mock positions with no loss
        self.order_manager.refresh_positions.return_value = {
            "net": [
                {
                    "tradingsymbol": "NIFTY25APR18000CE",
                    "unrealised_pnl": 5000
                }
            ]
        }
        
        # Call method
        result = self.risk_manager.check_shutdown_condition()
        
        # Verify
        self.assertFalse(result)
        
        # Mock positions with loss exceeding threshold
        self.order_manager.refresh_positions.return_value = {
            "net": [
                {
                    "tradingsymbol": "NIFTY25APR18000CE",
                    "unrealised_pnl": -70000  # More than 12.5% of 500000
                }
            ]
        }
        
        # Call method
        result = self.risk_manager.check_shutdown_condition()
        
        # Verify
        self.assertTrue(result)
    
    def test_check_profit_exit_condition(self):
        """Test checking profit exit condition"""
        # Mock positions with profit below threshold
        self.order_manager.refresh_positions.return_value = {
            "net": [
                {
                    "tradingsymbol": "NIFTY25APR18000CE",
                    "quantity": -50,
                    "sell_price": 100,
                    "instrument_token": 12345
                }
            ]
        }
        self.order_manager.get_ltp.return_value = 90  # 10% profit
        
        # Call method
        result = self.risk_manager.check_profit_exit_condition(12345, "CE")
        
        # Verify
        self.assertFalse(result)
        
        # Mock positions with profit exceeding threshold
        self.order_manager.refresh_positions.return_value = {
            "net": [
                {
                    "tradingsymbol": "NIFTY25APR18000CE",
                    "quantity": -50,
                    "sell_price": 100,
                    "instrument_token": 12345
                }
            ]
        }
        self.order_manager.get_ltp.return_value = 50  # 50% profit, 50 points * 50 quantity = 2500 points
        
        # Call method
        result = self.risk_manager.check_profit_exit_condition(12345, "CE")
        
        # Verify
        self.assertTrue(result)
    
    def test_calculate_position_profit_percentage(self):
        """Test calculating position profit percentage"""
        # Test short position with profit
        position = {
            "tradingsymbol": "NIFTY25APR18000CE",
            "quantity": -50,
            "sell_price": 100,
            "instrument_token": 12345
        }
        self.order_manager.get_ltp.return_value = 75  # 25% profit
        
        # Call method
        result = self.risk_manager.calculate_position_profit_percentage(position)
        
        # Verify
        self.assertEqual(result, 25.0)
        
        # Test long position with profit
        position = {
            "tradingsymbol": "NIFTY25APR18000CE",
            "quantity": 50,
            "buy_price": 100,
            "instrument_token": 12345
        }
        self.order_manager.get_ltp.return_value = 125  # 25% profit
        
        # Call method
        result = self.risk_manager.calculate_position_profit_percentage(position)
        
        # Verify
        self.assertEqual(result, 25.0)
    
    def test_is_trading_allowed(self):
        """Test checking if trading is allowed"""
        # Mock current time within trading hours on a trading day
        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime.datetime(2025, 4, 21, 10, 30)  # Monday 10:30 AM
            mock_datetime.strftime.return_value = "Monday"
            
            # Call method
            result = self.risk_manager.is_trading_allowed()
            
            # Verify
            self.assertTrue(result)
        
        # Mock current time outside trading hours
        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime.datetime(2025, 4, 21, 8, 30)  # Monday 8:30 AM
            mock_datetime.strftime.return_value = "Monday"
            
            # Call method
            result = self.risk_manager.is_trading_allowed()
            
            # Verify
            self.assertFalse(result)
        
        # Mock current time on a non-trading day
        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime.datetime(2025, 4, 20, 10, 30)  # Sunday 10:30 AM
            mock_datetime.strftime.return_value = "Sunday"
            
            # Call method
            result = self.risk_manager.is_trading_allowed()
            
            # Verify
            self.assertFalse(result)
    
    def test_check_position_loss_threshold(self):
        """Test checking position loss threshold"""
        # Test position with loss below threshold
        position = {
            "tradingsymbol": "NIFTY25APR18000CE",
            "quantity": 50,
            "buy_price": 100,
            "instrument_token": 12345
        }
        self.order_manager.get_ltp.return_value = 90  # 10% loss
        
        # Call method
        result = self.risk_manager.check_position_loss_threshold(position)
        
        # Verify
        self.assertFalse(result)
        
        # Test position with loss exceeding threshold
        position = {
            "tradingsymbol": "NIFTY25APR18000CE",
            "quantity": 50,
            "buy_price": 100,
            "instrument_token": 12345
        }
        self.order_manager.get_ltp.return_value = 70  # 30% loss
        
        # Call method
        result = self.risk_manager.check_position_loss_threshold(position)
        
        # Verify
        self.assertTrue(result)

if __name__ == "__main__":
    unittest.main()
