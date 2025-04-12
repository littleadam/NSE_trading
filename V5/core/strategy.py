import logging
from datetime import datetime, timedelta
from kiteconnect import KiteConnect
import config
from utils.helpers import calculate_atm_strike, validate_expiry

logger = logging.getLogger(__name__)

class OptionsStrategy:
    def __init__(self, kite_client, spot_price):
        self.kite = kite_client
        self.spot = spot_price
        self.instruments = self._fetch_nifty_instruments()
        self.expiries = self._process_expiries()

    def _fetch_nifty_instruments(self):
        """Fetch and filter Nifty option instruments"""
        try:
            all_instruments = self.kite.instruments('NFO')
            return [
                inst for inst in all_instruments 
                if inst['name'] == 'NIFTY' 
                and inst['instrument_type'] in ['CE', 'PE']
            ]
        except Exception as e:
            logger.error(f"Failed to fetch instruments: {str(e)}")
            raise RuntimeError("Instrument fetch failed") from e

    def _process_expiries(self):
        """Process and validate expiry dates"""
        raw_expiries = sorted({inst['expiry'] for inst in self.instruments if inst['expiry']})
        return [datetime.strptime(exp, '%Y-%m-%d').date() for exp in raw_expiries]

    def get_far_expiry(self):
        """Select third monthly expiry from current date"""
        monthly_expiries = sorted([
            exp for exp in self.expiries
            if validate_expiry(exp, monthly=True)
        ])
        
        if not monthly_expiries:
            raise ValueError("No valid monthly expiries found")
        
        current_expiry_index = 0
        for idx, exp in enumerate(monthly_expiries):
            if exp > datetime.now().date():
                current_expiry_index = idx
                break
                
        target_index = min(current_expiry_index + 3, len(monthly_expiries) - 1)
        return monthly_expiries[target_index]

    def calculate_straddle_strikes(self, expiry):
        """Calculate straddle strikes with bias"""
        base_strike = calculate_atm_strike(self.spot, config.BIAS)
        strikes = self._get_valid_strikes(expiry, base_strike)
        
        if not strikes['CE'] or not strikes['PE']:
            raise ValueError(f"No straddle strikes found for {base_strike}")
            
        return {
            'ce': strikes['CE'][0]['strike'],
            'pe': strikes['PE'][0]['strike'],
            'expiry': expiry
        }

    def calculate_strangle_strikes(self, expiry):
        """Calculate strangle strikes ±1000 from spot"""
        ce_strike = calculate_atm_strike(self.spot + 1000, 0)
        pe_strike = calculate_atm_strike(self.spot - 1000, 0)
        
        ce_candidates = self._get_valid_strikes(expiry, ce_strike)['CE']
        pe_candidates = self._get_valid_strikes(expiry, pe_strike)['PE']
        
        if not ce_candidates or not pe_candidates:
            raise ValueError(f"Strangle strikes unavailable for {ce_strike}/{pe_strike}")
            
        return {
            'ce': ce_candidates[0]['strike'],
            'pe': pe_candidates[0]['strike'],
            'expiry': expiry
        }

    def _get_valid_strikes(self, expiry, base_strike):
        """Get valid strikes near target price for given expiry"""
        filtered = {
            'CE': [],
            'PE': []
        }
        
        for inst in self.instruments:
            if inst['expiry'] != expiry.isoformat():
                continue
                
            if inst['instrument_type'] == 'CE':
                filtered['CE'].append({
                    'strike': inst['strike'],
                    'tradingsymbol': inst['tradingsymbol']
                })
            elif inst['instrument_type'] == 'PE':
                filtered['PE'].append({
                    'strike': inst['strike'],
                    'tradingsymbol': inst['tradingsymbol']
                })
                
        # Sort and find nearest strikes
        for opt_type in ['CE', 'PE']:
            filtered[opt_type].sort(key=lambda x: abs(x['strike'] - base_strike))
            
        return filtered

    def get_strategy_parameters(self, strategy_type, expiry):
        """Main entry point for strategy calculations"""
        if strategy_type == 'STRADDLE':
            return self.calculate_straddle_strikes(expiry)
        elif strategy_type == 'STRANGLE':
            return self.calculate_strangle_strikes(expiry)
        else:
            raise ValueError(f"Unknown strategy type: {strategy_type}")

    def find_conflict_free_strikes(self, strategy_type, base_params):
        """Recursive strike adjustment for conflicts"""
        existing_positions = self._get_existing_positions()
        adjusted_params = base_params.copy()
        conflict_found = False
        
        for opt_type in ['CE', 'PE']:
            for position in existing_positions:
                if position['strike'] == adjusted_params[opt_type]:
                    new_strike = self._adjust_strike(
                        strategy_type, 
                        opt_type, 
                        adjusted_params[opt_type]
                    )
                    logger.info(f"Adjusting {opt_type} strike from {adjusted_params[opt_type]} to {new_strike}")
                    adjusted_params[opt_type] = new_strike
                    conflict_found = True
                    
        return adjusted_params if not conflict_found else \
            self.find_conflict_free_strikes(strategy_type, adjusted_params)

    def _adjust_strike(self, strategy_type, opt_type, current_strike):
        """Calculate next valid strike based on strategy"""
        if strategy_type == 'STRADDLE':
            return current_strike + (50 if opt_type == 'CE' else -50)
        elif strategy_type == 'STRANGLE':
            return current_strike + (100 if opt_type == 'CE' else -100)
        return current_strike

    def _get_existing_positions(self):
        """Retrieve current option positions"""
        positions = self.kite.positions()['net']
        return [
            {
                'tradingsymbol': p['tradingsymbol'],
                'strike': self._extract_strike(p['tradingsymbol']),
                'expiry': datetime.strptime(p['expiry'], '%Y-%m-%d').date(),
                'quantity': p['quantity']
            }
            for p in positions 
            if p['product'] == 'MIS' 
            and p['instrument_type'] in ['CE', 'PE']
        ]

    def _extract_strike(self, tradingsymbol):
        """Extract strike price from tradingsymbol"""
        parts = tradingsymbol.split(' ')
        return float(parts[-2])
