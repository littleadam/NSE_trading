# core/strategy.py
import logging
from datetime import datetime, timedelta
from calendar import monthcalendar
from typing import Dict, List

from kiteconnect import KiteConnect
import config
from utils.helpers import calculate_atm_strike, validate_expiry, Helpers

logger = logging.getLogger(__name__)

class OptionsStrategy:
    def __init__(self, kite_client: KiteConnect, spot_price: float):
        self.kite = kite_client
        self.spot = spot_price
        self.instruments = self._fetch_nifty_instruments()
        self.expiries = self._process_expiries()
        self.position_tracker = PositionTracker(kite_client)

    def _fetch_nifty_instruments(self) -> List[Dict]:
        """Fetch and filter Nifty option instruments with error handling"""
        try:
            all_instruments = Helpers.fetch_instruments(self.kite)
            return [
                inst for inst in all_instruments 
                if inst['name'] == 'NIFTY' 
                and inst['instrument_type'] in ['CE', 'PE']
                and inst['expiry'] is not None
            ]
        except Exception as e:
            logger.error(f"Instrument fetch failed: {str(e)}")
            raise RuntimeError("Critical instrument data unavailable") from e

    def _process_expiries(self) -> List[datetime.date]:
        """Process and validate expiry dates with holiday checks"""
        raw_expiries = sorted({datetime.strptime(inst['expiry'], '%Y-%m-%d').date() 
                             for inst in self.instruments if inst['expiry']})
        return [exp for exp in raw_expiries if config.TRADING_CALENDAR.is_trading_day(exp)]

    @staticmethod
    def is_monthly_expiry(expiry_date: datetime.date) -> bool:
        """Check if date is monthly expiry (last Thursday of month)"""
        last_thursday = max(
            week[3] 
            for week in monthcalendar(expiry_date.year, expiry_date.month)
            if week[3] != 0
        )
        return expiry_date.day == last_thursday

    def get_far_expiry(self) -> datetime.date:
        """Select third valid monthly expiry from current date"""
        monthly_expiries = sorted([
            exp for exp in self.expiries 
            if self.is_monthly_expiry(exp)
        ], reverse=False)

        if not monthly_expiries:
            raise ValueError("No valid monthly expiries available")

        # Find first expiry after current date
        current_date = datetime.now().date()
        future_expiries = [exp for exp in monthly_expiries if exp > current_date]
        
        if not future_expiries:
            return monthly_expiries[-1]  # Fallback to last available
        
        target_index = min(2, len(future_expiries)-1)
        return future_expiries[target_index]

    def calculate_straddle_strikes(self, expiry: datetime.date) -> Dict:
        """Calculate straddle strikes with bias and validation"""
        base_strike = calculate_atm_strike(self.spot, config.BIAS)
        valid_strikes = self._get_valid_strikes(expiry, base_strike)
        
        if not valid_strikes['CE'] or not valid_strikes['PE']:
            raise ValueError(f"No valid straddle strikes at {base_strike}")
            
        return {
            'ce': valid_strikes['CE'][0]['strike'],
            'pe': valid_strikes['PE'][0]['strike'],
            'expiry': expiry,
            'entry_time': datetime.now()
        }

    def calculate_strangle_strikes(self, expiry: datetime.date) -> Dict:
        """Calculate strangle strikes with minimum 1000pt distance validation"""
        ce_strike = calculate_atm_strike(self.spot + 1000, 0)
        pe_strike = calculate_atm_strike(self.spot - 1000, 0)
        
        # Ensure minimum distance requirements
        while (ce_strike - self.spot) < 1000:
            ce_strike += 100
        while (self.spot - pe_strike) < 1000:
            pe_strike -= 100

        ce_candidates = self._get_valid_strikes(expiry, ce_strike)['CE']
        pe_candidates = self._get_valid_strikes(expiry, pe_strike)['PE']
        
        if not ce_candidates or not pe_candidates:
            raise ValueError(f"Invalid strangle strikes {ce_strike}/{pe_strike}")
            
        return {
            'ce': ce_candidates[0]['strike'],
            'pe': pe_candidates[0]['strike'],
            'expiry': expiry,
            'entry_time': datetime.now()
        }

    def _get_valid_strikes(self, expiry: datetime.date, base_strike: float) -> Dict:
        """Get valid strikes sorted by proximity to target"""
        strikes = {'CE': [], 'PE': []}
        
        for inst in self.instruments:
            inst_expiry = datetime.strptime(inst['expiry'], '%Y-%m-%d').date()
            if inst_expiry != expiry:
                continue
                
            if inst['instrument_type'] == 'CE':
                strikes['CE'].append({
                    'strike': inst['strike'],
                    'tradingsymbol': inst['tradingsymbol']
                })
            elif inst['instrument_type'] == 'PE':
                strikes['PE'].append({
                    'strike': inst['strike'],
                    'tradingsymbol': inst['tradingsymbol']
                })
        
        # Sort by proximity to target strike
        for opt_type in ['CE', 'PE']:
            strikes[opt_type].sort(key=lambda x: abs(x['strike'] - base_strike))
            
        return strikes

    def get_strategy_parameters(self, strategy_type: str, expiry: datetime.date) -> Dict:
        """Main strategy parameter calculator with validation"""
        if not config.TRADING_CALENDAR.is_trading_day(datetime.now().date()):
            raise RuntimeError("Strategy execution attempted on non-trading day")

        if strategy_type == 'STRADDLE':
            params = self.calculate_straddle_strikes(expiry)
        elif strategy_type == 'STRANGLE':
            params = self.calculate_strangle_strikes(expiry)
        else:
            raise ValueError(f"Unsupported strategy: {strategy_type}")

        return self.find_conflict_free_strikes(strategy_type, params)

    def find_conflict_free_strikes(self, strategy_type: str, base_params: Dict) -> Dict:
        """Recursive strike adjustment with position conflict checks"""
        self.position_tracker.update_positions()
        existing_positions = self.position_tracker.get_conflicts(
            strategy_type,
            base_params['expiry']
        )
        
        if not existing_positions:
            return base_params

        logger.info(f"Adjusting strikes due to {len(existing_positions)} conflicts")
        adjusted = base_params.copy()
        for opt_type in ['CE', 'PE']:
            conflict = next(
                (p for p in existing_positions 
                 if abs(p['strike'] - adjusted[opt_type]) <= config.ADJACENCY_GAP),
                None
            )
            if conflict:
                adjusted[opt_type] = self._calculate_adjusted_strike(
                    strategy_type,
                    opt_type,
                    adjusted[opt_type]
                )
                
        return self.find_conflict_free_strikes(strategy_type, adjusted)

    def _calculate_adjusted_strike(self, strategy_type: str, opt_type: str, current_strike: float) -> float:
        """Calculate next valid strike based on strategy rules"""
        adjustment = config.ADJACENCY_GAP * (1 if opt_type == 'CE' else -1)
        if strategy_type == 'STRANGLE':
            adjustment *= 2  # Wider adjustment for strangle
        return current_strike + adjustment

class PositionTracker:
    """Helper class for position conflict detection"""
    def __init__(self, kite: KiteConnect):
        self.kite = kite
        self.positions = []

    def update_positions(self):
        """Refresh positions from broker API"""
        try:
            self.positions = [
                p for p in self.kite.positions()['net']
                if p['product'] == 'MIS' 
                and p['instrument_type'] in ['CE', 'PE']
            ]
        except Exception as e:
            logger.error(f"Position update failed: {str(e)}")
            raise

    def get_conflicts(self, strategy_type: str, expiry: datetime.date) -> List[Dict]:
        """Identify conflicting positions for given strategy/expiry"""
        return [
            p for p in self.positions
            if datetime.strptime(p['expiry'], '%Y-%m-%d').date() == expiry
            and (
                (strategy_type == 'STRADDLE' and 
                 abs(p['strike'] - p['average_price']) <= config.ADJACENCY_GAP) 
                or
                (strategy_type == 'STRANGLE' and 
                 (p['strike'] >= (p['average_price'] + 800) or 
                  p['strike'] <= (p['average_price'] - 800)))
            )
  ]
