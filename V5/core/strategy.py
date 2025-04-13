# core/strategy.py
import logging
from datetime import datetime, timedelta
from calendar import monthcalendar
from typing import Dict, List

from kiteconnect import KiteConnect
from config import Config
from utils.helpers import Helpers
from utils.position_tracker import PositionTracker
from utils.logger import logger, log_function, DecisionLogger

logger = logging.getLogger(__name__)

class OptionsStrategy:
    def __init__(self, kite_client: KiteConnect, spot_price: float):
        self.kite = kite_client
        self.spot = spot_price
        self.instruments = self._fetch_nifty_instruments()
        self.expiries = self._process_expiries()
        self.position_tracker = PositionTracker(kite_client)

    @log_function
    def _fetch_nifty_instruments(self) -> List[Dict]:
        """Fetch and filter Nifty option instruments with error handling"""
        try:
            all_instruments = Helpers.fetch_instruments(self.kite)
            nifty_instruments = [
                inst for inst in all_instruments 
                if inst['name'] == 'NIFTY' 
                and inst['instrument_type'] in ['CE', 'PE']
                and inst['expiry'] is not None
            ]
            if not nifty_instruments:
                raise ValueError("No NIFTY instruments found")
            return nifty_instruments
        except Exception as e:
            logger.error(f"Instrument fetch failed: {str(e)}")
            raise RuntimeError("Critical instrument data unavailable") from e

    @log_function
    def _process_expiries(self) -> List[datetime.date]:
        """Process and validate expiry dates with holiday checks"""
        raw_expiries = sorted({
            datetime.strptime(inst['expiry'], '%Y-%m-%d').date() 
            for inst in self.instruments if inst['expiry']
        })
        valid_expiries = [exp for exp in raw_expiries 
                         if Config.TRADING_CALENDAR.is_trading_day(exp)]
        if not valid_expiries:
            raise ValueError("No valid trading expiries available")
        return valid_expiries

    @staticmethod
    def is_monthly_expiry(expiry_date: datetime.date) -> bool:
        """Check if date is monthly expiry (last Thursday of month)"""
        last_thursday = max(
            week[3] 
            for week in monthcalendar(expiry_date.year, expiry_date.month)
            if week[3] != 0
        )
        return expiry_date.day == last_thursday

    @log_function
    def get_far_expiry(self) -> datetime.date:
        """Select third valid monthly expiry from current date"""
        monthly_expiries = sorted([
            exp for exp in self.expiries 
            if self.is_monthly_expiry(exp)
        ], reverse=False)

        if not monthly_expiries:
            raise ValueError("No valid monthly expiries available")

        current_date = datetime.now().date()
        future_expiries = [exp for exp in monthly_expiries if exp > current_date]
        
        try:
            if not future_expiries:
                return monthly_expiries[-1]
            
            target_index = min(Config.FAR_MONTH_INDEX, len(future_expiries)-1)
            return future_expiries[target_index]
        except IndexError:
            return monthly_expiries[-1]

    @log_function
    def calculate_straddle_strikes(self, expiry: datetime.date) -> Dict:
        """Calculate straddle strikes with bias and validation"""
        base_strike = Helpers.get_nearest_strike(self.spot, Config.BIAS)
        valid_strikes = self._get_valid_strikes(expiry, base_strike)
        
        if not valid_strikes['CE'] or not valid_strikes['PE']:
            raise ValueError(f"No valid straddle strikes at {base_strike}")
            
        return {
            'ce': valid_strikes['CE'][0]['strike'],
            'pe': valid_strikes['PE'][0]['strike'],
            'expiry': expiry,
            'entry_time': datetime.now()
        }

    @log_function
    def calculate_strangle_strikes(self, expiry: datetime.date) -> Dict:
        """Calculate strangle strikes with configurable gap"""
        ce_strike = Helpers.get_nearest_strike(
            self.spot + Config.STRANGLE_GAP, 
            Config.ADJACENCY_GAP
        )
        pe_strike = Helpers.get_nearest_strike(
            self.spot - Config.STRANGLE_GAP,
            Config.ADJACENCY_GAP
        )
        
        # Ensure minimum distance requirements
        while (ce_strike - self.spot) < Config.STRANGLE_GAP:
            ce_strike += Config.ADJACENCY_GAP
        while (self.spot - pe_strike) < Config.STRANGLE_GAP:
            pe_strike -= Config.ADJACENCY_GAP

        ce_candidates = self._get_valid_strikes(expiry, ce_strike)['CE']
        pe_candidates = self._get_valid_strikes(expiry, pe_strike)['PE']
        
        if not ce_candidates or not pe_candidates:
            raise ValueError(f"Invalid strangle strikes {ce_strike}/{pe_strike}")
            
        DecisionLogger.log_decision({
            "event": "strangle_strikes_calculated",
            "ce_strike": ce_strike,
            "pe_strike": pe_strike,
            "spot": self.spot
        })
            
        return {
            'ce': ce_candidates[0]['strike'],
            'pe': pe_candidates[0]['strike'],
            'expiry': expiry,
            'entry_time': datetime.now()
        }

    @log_function
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
        
        for opt_type in ['CE', 'PE']:
            strikes[opt_type].sort(key=lambda x: abs(x['strike'] - base_strike))
            
        return strikes

    @log_function
    def get_strategy_parameters(self, strategy_type: str, expiry: datetime.date) -> Dict:
        """Main strategy parameter calculator with validation"""
        if not Config.TRADING_CALENDAR.is_trading_day(datetime.now().date()):
            raise RuntimeError("Strategy execution attempted on non-trading day")

        if strategy_type == 'STRADDLE':
            params = self.calculate_straddle_strikes(expiry)
        elif strategy_type == 'STRANGLE':
            params = self.calculate_strangle_strikes(expiry)
        else:
            raise ValueError(f"Unsupported strategy: {strategy_type}")

        return self.find_conflict_free_strikes(strategy_type, params)

    @log_function
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
                 if abs(p['strike'] - adjusted[opt_type]) <= Config.ADJACENCY_GAP),
                None
            )
            if conflict:
                adjusted[opt_type] = self._calculate_adjusted_strike(
                    strategy_type,
                    opt_type,
                    adjusted[opt_type]
                )
                
        return self.find_conflict_free_strikes(strategy_type, adjusted)

    @log_function
    def _calculate_adjusted_strike(self, strategy_type: str, opt_type: str, current_strike: float) -> float:
        """Calculate next valid strike based on strategy rules"""
        adjustment = Config.ADJACENCY_GAP * (1 if opt_type == 'CE' else -1)
        if strategy_type == 'STRANGLE':
            adjustment *= (Config.STRANGLE_GAP / Config.ADJACENCY_GAP)
        new_strike = current_strike + adjustment
        logger.debug(f"Adjusted {opt_type} strike from {current_strike} to {new_strike}")
        return new_strike
