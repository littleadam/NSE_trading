# tests/test_strategies.py
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import pandas as pd
from core.strategy import OptionsStrategy
from config import Config
from kiteconnect import KiteConnect

@pytest.fixture
def mock_kite():
    kite = MagicMock(spec=KiteConnect)
    return kite

@pytest.fixture
def mock_instruments():
    return pd.DataFrame([{
        'tradingsymbol': 'NIFTY23NOV18000CE',
        'instrument_token': '128563201',
        'expiry': '2023-11-23',
        'strike': 18000.0,
        'instrument_type': 'CE',
        'name': 'NIFTY'
    }, {
        'tradingsymbol': 'NIFTY23NOV18000PE',
        'instrument_token': '128563202',
        'expiry': '2023-11-23',
        'strike': 18000.0,
        'instrument_type': 'PE',
        'name': 'NIFTY'
    }])

@pytest.fixture
def strategy(mock_kite, mock_instruments):
    with patch('core.strategy.Helpers.fetch_instruments') as mock_fetch:
        mock_fetch.return_value = mock_instruments
        return OptionsStrategy(mock_kite, 18000.0)

class TestOptionsStrategy:
    def test_fetch_nifty_instruments(self, strategy):
        instruments = strategy._fetch_nifty_instruments()
        assert len(instruments) > 0
        assert all(inst['name'] == 'NIFTY' for inst in instruments)
        
    def test_process_expiries(self, strategy):
        expiries = strategy._process_expiries()
        assert len(expiries) > 0
        assert isinstance(expiries[0], datetime.date)

    @pytest.mark.parametrize("date,expected", [
        (datetime(2023, 11, 30).date(), True),
        (datetime(2023, 11, 15).date(), False)
    ])
    def test_is_monthly_expiry(self, date, expected):
        assert OptionsStrategy.is_monthly_expiry(date) == expected

    def test_get_far_expiry(self, strategy):
        expiry = strategy.get_far_expiry()
        assert isinstance(expiry, datetime.date)
        assert expiry > datetime.now().date()

    @pytest.mark.parametrize("spot,bias,expected", [
        (18050, 0, 18000),
        (18050, 100, 18100),
        (17975, -50, 17900)
    ])
    def test_calculate_straddle_strikes(self, strategy, spot, bias, expected):
        Config.BIAS = bias
        strategy.spot = spot
        result = strategy.calculate_straddle_strikes(datetime.now().date())
        assert result['ce'] == expected + bias
        assert result['pe'] == expected - bias

    @pytest.mark.parametrize("spot,gap,expected_ce,expected_pe", [
        (18000, 1000, 19000, 17000),
        (18500, 500, 19000, 18000)
    ])
    def test_calculate_strangle_strikes(self, strategy, spot, gap, expected_ce, expected_pe):
        Config.STRANGLE_GAP = gap
        strategy.spot = spot
        result = strategy.calculate_strangle_strikes(datetime.now().date())
        assert result['ce'] >= spot + gap
        assert result['pe'] <= spot - gap

    def test_get_valid_strikes(self, strategy):
        strikes = strategy._get_valid_strikes(datetime.now().date(), 18000)
        assert 'CE' in strikes
        assert 'PE' in strikes
        assert len(strikes['CE']) > 0
        assert len(strikes['PE']) > 0

    @pytest.mark.parametrize("strategy_type", ['STRADDLE', 'STRANGLE'])
    def test_get_strategy_parameters(self, strategy, strategy_type):
        params = strategy.get_strategy_parameters(strategy_type, datetime.now().date())
        assert 'ce' in params
        assert 'pe' in params
        assert 'expiry' in params

    def test_conflict_free_strikes(self, strategy):
        with patch('core.strategy.PositionTracker') as mock_tracker:
            mock_tracker.return_value.get_conflicts.return_value = [{
                'strike': 18000,
                'expiry': datetime.now().date()
            }]
            params = strategy.find_conflict_free_strikes('STRADDLE', {
                'ce': 18000,
                'pe': 18000,
                'expiry': datetime.now().date()
            })
            assert params['ce'] != 18000
            assert params['pe'] != 18000

    def test_invalid_strategy_type(self, strategy):
        with pytest.raises(ValueError):
            strategy.get_strategy_parameters('INVALID', datetime.now().date())

    def test_no_instruments_error(self):
        with patch('core.strategy.Helpers.fetch_instruments') as mock_fetch:
            mock_fetch.return_value = pd.DataFrame()
            with pytest.raises(RuntimeError):
                OptionsStrategy(MagicMock(), 18000.0)

    def test_straddle_edge_case(self, strategy):
        strategy.spot = 17950
        Config.BIAS = 100
        result = strategy.calculate_straddle_strikes(datetime.now().date())
        assert result['ce'] == 18000
        assert result['pe'] == 18000

    def test_strangle_adjustment(self, strategy):
        Config.STRANGLE_GAP = 800
        strategy.spot = 18000
        result = strategy.calculate_strangle_strikes(datetime.now().date())
        assert (result['ce'] - 18000) >= 800
        assert (18000 - result['pe']) >= 800

    def test_expired_instruments(self, strategy):
        old_date = (datetime.now() - timedelta(days=365)).date()
        with pytest.raises(ValueError):
            strategy.calculate_straddle_strikes(old_date)

    def test_position_tracker_integration(self, strategy):
        with patch('core.strategy.PositionTracker') as mock_tracker:
            mock_tracker.return_value.get_conflicts.return_value = []
            params = strategy.find_conflict_free_strikes('STRADDLE', {
                'ce': 18000,
                'pe': 18000,
                'expiry': datetime.now().date()
            })
            assert params['ce'] == 18000
            assert params['pe'] == 18000

if __name__ == "__main__":
    pytest.main(["-v", "-s", "tests/test_strategies.py"])
