# tests/test_strategies.py
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, date
import pandas as pd
from kiteconnect import KiteConnect

# Import the module to test
from core.strategy import OptionsStrategy

class TestOptionsStrategy(unittest.TestCase):
    def setUp(self):
        # Mock Kite client
        self.mock_kite = MagicMock(spec=KiteConnect)
        
        # Current date for testing
        self.today = date(2023, 12, 15)  # Fixed date for consistent testing
        self.mock_spot_price = 19500.0
        
        # Mock instruments data
        self.mock_instruments = [
            {
                'tradingsymbol': 'NIFTY23DEC19500CE',
                'instrument_token': 12345,
                'expiry': '2023-12-28',
                'strike': 19500.0,
                'instrument_type': 'CE',
                'name': 'NIFTY'
            },
            {
                'tradingsymbol': 'NIFTY23DEC19500PE',
                'instrument_token': 12346,
                'expiry': '2023-12-28',
                'strike': 19500.0,
                'instrument_type': 'PE',
                'name': 'NIFTY'
            },
            # For strangle tests
            {
                'tradingsymbol': 'NIFTY23DEC20500CE',
                'instrument_token': 12347,
                'expiry': '2023-12-28',
                'strike': 20500.0,
                'instrument_type': 'CE',
                'name': 'NIFTY'
            },
            {
                'tradingsymbol': 'NIFTY23DEC18500PE',
                'instrument_token': 12348,
                'expiry': '2023-12-28',
                'strike': 18500.0,
                'instrument_type': 'PE',
                'name': 'NIFTY'
            },
            # Monthly expiry
            {
                'tradingsymbol': 'NIFTY24JAN19500CE',
                'instrument_token': 12349,
                'expiry': '2024-01-25',
                'strike': 19500.0,
                'instrument_type': 'CE',
                'name': 'NIFTY'
            }
        ]
        
        # Patch datetime.date.today() to return fixed date
        self.date_patcher = patch('datetime.date')
        mock_date = self.date_patcher.start()
        mock_date.today.return_value = self.today
        
        # Initialize strategy with mock data
        self.strategy = OptionsStrategy(self.mock_kite, self.mock_spot_price)
        
        # Mock helpers.fetch_instruments
        self.strategy._fetch_nifty_instruments = MagicMock(return_value=self.mock_instruments)
        
    def tearDown(self):
        self.date_patcher.stop()

    def test_initialization(self):
        """Test strategy initialization with mock data"""
        self.assertEqual(self.strategy.spot, self.mock_spot_price)
        self.assertIsInstance(self.strategy.instruments, list)
        self.assertGreater(len(self.strategy.instruments), 0)
        
    def test_is_monthly_expiry(self):
        """Test monthly expiry identification"""
        # Last Thursday of December 2023 is 28th
        self.assertTrue(self.strategy.is_monthly_expiry(date(2023, 12, 28)))
        # Not last Thursday
        self.assertFalse(self.strategy.is_monthly_expiry(date(2023, 12, 21)))
        
    def test_get_far_expiry(self):
        """Test far expiry calculation"""
        # Mock expiries including monthly
        mock_expiries = [
            date(2023, 12, 28),  # Weekly
            date(2024, 1, 25),    # Monthly
            date(2024, 2, 29),    # Monthly
            date(2024, 3, 28)     # Monthly
        ]
        self.strategy.expiries = mock_expiries
        
        # FAR_MONTH_INDEX=3 should return March expiry
        far_expiry = self.strategy.get_far_expiry()
        self.assertEqual(far_expiry, date(2024, 3, 28))
        
        # Test when fewer expiries exist
        self.strategy.expiries = mock_expiries[:2]
        far_expiry = self.strategy.get_far_expiry()
        self.assertEqual(far_expiry, date(2024, 1, 25))
        
    def test_calculate_straddle_strikes(self):
        """Test straddle strike calculation"""
        expiry = date(2023, 12, 28)
        result = self.strategy.calculate_straddle_strikes(expiry)
        
        # Should return nearest strikes to spot (19500)
        self.assertEqual(result['ce'], 19500.0)
        self.assertEqual(result['pe'], 19500.0)
        self.assertEqual(result['expiry'], expiry)
        self.assertIsInstance(result['entry_time'], datetime)
        
        # Test with bias
        with patch('config.Config.BIAS', 100):
            result = self.strategy.calculate_straddle_strikes(expiry)
            self.assertEqual(result['ce'], 19600.0)
            self.assertEqual(result['pe'], 19600.0)
            
    def test_calculate_strangle_strikes(self):
        """Test strangle strike calculation"""
        expiry = date(2023, 12, 28)
        with patch('config.Config.STRANGLE_GAP', 1000):
            result = self.strategy.calculate_strangle_strikes(expiry)
            
            # Should return strikes ±1000 from spot (19500)
            self.assertEqual(result['ce'], 20500.0)
            self.assertEqual(result['pe'], 18500.0)
            self.assertEqual(result['expiry'], expiry)
            self.assertIsInstance(result['entry_time'], datetime)
            
    def test_get_valid_strikes(self):
        """Test strike filtering by expiry and type"""
        expiry = date(2023, 12, 28)
        strikes = self.strategy._get_valid_strikes(expiry, 19500.0)
        
        # Should return sorted strikes by proximity to base_strike
        self.assertEqual(len(strikes['CE']), 2)  # 19500CE and 20500CE
        self.assertEqual(len(strikes['PE']), 2)  # 19500PE and 18500PE
        self.assertEqual(strikes['CE'][0]['strike'], 19500.0)  # Nearest first
        self.assertEqual(strikes['PE'][0]['strike'], 19500.0)
        
    def test_get_strategy_parameters_straddle(self):
        """Test complete straddle parameter generation"""
        expiry = date(2023, 12, 28)
        params = self.strategy.get_strategy_parameters('STRADDLE', expiry)
        
        self.assertEqual(params['ce'], 19500.0)
        self.assertEqual(params['pe'], 19500.0)
        self.assertEqual(params['expiry'], expiry)
        
    def test_get_strategy_parameters_strangle(self):
        """Test complete strangle parameter generation"""
        expiry = date(2023, 12, 28)
        with patch('config.Config.STRANGLE_GAP', 1000):
            params = self.strategy.get_strategy_parameters('STRANGLE', expiry)
            
            self.assertEqual(params['ce'], 20500.0)
            self.assertEqual(params['pe'], 18500.0)
            self.assertEqual(params['expiry'], expiry)
            
    def test_find_conflict_free_strikes(self):
        """Test strike adjustment with position conflicts"""
        expiry = date(2023, 12, 28)
        
        # Mock position tracker
        mock_tracker = MagicMock()
        mock_tracker.get_conflicts.return_value = [
            {'strike': 19500.0, 'expiry': expiry, 'instrument_type': 'CE'}
        ]
        self.strategy.position_tracker = mock_tracker
        
        # Test with straddle
        base_params = {
            'ce': 19500.0,
            'pe': 19500.0,
            'expiry': expiry,
            'entry_time': datetime.now()
        }
        
        with patch('config.Config.ADJACENCY_GAP', 100):
            adjusted = self.strategy.find_conflict_free_strikes('STRADDLE', base_params)
            
            # CE strike should be adjusted by ADJACENCY_GAP
            self.assertEqual(adjusted['ce'], 19600.0)
            # PE strike remains same
            self.assertEqual(adjusted['pe'], 19500.0)
            
    def test_calculate_adjusted_strike(self):
        """Test individual strike adjustment logic"""
        with patch('config.Config.ADJACENCY_GAP', 100):
            # CE strike should increase
            new_ce = self.strategy._calculate_adjusted_strike('STRADDLE', 'CE', 19500.0)
            self.assertEqual(new_ce, 19600.0)
            
            # PE strike should decrease
            new_pe = self.strategy._calculate_adjusted_strike('STRADDLE', 'PE', 19500.0)
            self.assertEqual(new_pe, 19400.0)
            
            # Strangle adjustments should be larger
            with patch('config.Config.STRANGLE_GAP', 1000):
                new_ce = self.strategy._calculate_adjusted_strike('STRANGLE', 'CE', 19500.0)
                self.assertEqual(new_ce, 20500.0)
                
    def test_invalid_strategy_type(self):
        """Test error handling for invalid strategy types"""
        with self.assertRaises(ValueError):
            self.strategy.get_strategy_parameters('INVALID', date(2023, 12, 28))
            
    def test_no_valid_strikes(self):
        """Test error handling when no valid strikes found"""
        # Empty instruments list
        self.strategy.instruments = []
        
        with self.assertRaises(ValueError):
            self.strategy.calculate_straddle_strikes(date(2023, 12, 28))
            
    def test_non_trading_day(self):
        """Test strategy execution on non-trading days"""
        mock_calendar = MagicMock()
        mock_calendar.is_trading_day.return_value = False
        with patch('config.Config.TRADING_CALENDAR', mock_calendar):
            with self.assertRaises(RuntimeError):
                self.strategy.get_strategy_parameters('STRADDLE', date(2023, 12, 28))

if __name__ == '__main__':
    unittest.main()
