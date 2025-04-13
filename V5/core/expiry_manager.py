# core/expiry_manager.py
import logging
import calendar
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pandas as pd
from config import (
    ADJACENCY_GAP,
    FAR_SELL_ADD,
    HEDGE_ONE_LOT,
    LOT_SIZE,
    TRADE_DAYS,
    HEDGE_PREMIUM_THRESHOLD,
    FAR_MONTH_INDEX,
    ROLLOVER_DAYS_THRESHOLD
)
from utils.helpers import Helpers

logger = logging.getLogger(__name__)

class ExpiryManager:
    def __init__(self, kite, order_manager, spot_price):
        self.kite = kite
        self.order_manager = order_manager
        self.spot = spot_price
        self.instruments = self._load_instruments()
        self.current_hedges = []
        self.current_far_expiry = self._get_initial_expiries()
        self.min_strike_distance = ADJACENCY_GAP * 2

    def _load_instruments(self):
        """Load and cache NFO instruments"""
        logger.info("Loading NFO instruments")
        return pd.DataFrame(self.kite.instruments("NFO"))

    def _is_monthly_expiry(self, date_obj):
        """Check if date is last Thursday of the month"""
        last_thursday = max(
            week[3] 
            for week in calendar.monthcalendar(date_obj.year, date_obj.month)
            if week[3] != 0
        )
        return date_obj.day == last_thursday

    def _get_initial_expiries(self):
        """Identify initial weekly and far month expiries"""
        all_expiries = sorted({
            datetime.strptime(e, '%Y-%m-%d') 
            for e in self.instruments[self.instruments['name'] == 'NIFTY']['expiry']
            if e != ''
        })
        
        monthly_expiries = [e for e in all_expiries if self._is_monthly_expiry(e)]
        weekly_expiries = [e for e in all_expiries if not self._is_monthly_expiry(e)]
        
        try:
            far_month = (
                monthly_expiries[FAR_MONTH_INDEX] 
                if len(monthly_expiries) > FAR_MONTH_INDEX
                else monthly_expiries[-1]
            )
        except IndexError:
            far_month = monthly_expiries[-1] if monthly_expiries else None
            
        return {
            'weekly': weekly_expiries[0] if weekly_expiries else None,
            'far_month': far_month
        }

    def get_weekly_expiries(self):
        """Get sorted list of weekly expiries (non-monthly)"""
        return sorted([
            e for e in self._get_all_expiries()
            if not self._is_monthly_expiry(e)
        ])

    def _get_all_expiries(self):
        """Get all unique expiry dates"""
        return sorted({
            datetime.strptime(e, '%Y-%m-%d')
            for e in self.instruments['expiry']
            if e != ''
        })

    def needs_rollover(self, hedge):
        """Determine if hedge needs rollover"""
        if not hedge:
            return False
            
        days_to_expiry = (hedge['expiry'] - datetime.now()).days
        return days_to_expiry <= ROLLOVER_DAYS_THRESHOLD

    def replace_expiring_hedges(self):
        """Roll over expiring weekly hedges to next series"""
        new_hedges = []
        for hedge in self.current_hedges:
            if self.needs_rollover(hedge):
                logger.info(f"Rolling over hedge: {hedge['tradingsymbol']}")
                
                try:
                    # Close existing position
                    self.order_manager.place_order(
                        hedge['tradingsymbol'],
                        hedge['quantity'],
                        self.kite.TRANSACTION_TYPE_BUY
                    )

                    # Calculate new parameters
                    new_expiry = self.get_next_weekly_expiry(hedge['expiry'])
                    new_strike = self.calculate_premium_based_strike(new_expiry)
                    
                    # Validate strike distance
                    if abs(new_strike - self.spot) < self.min_strike_distance:
                        new_strike = self._get_safe_strike(new_expiry)
                        
                    # Place new hedge
                    new_symbol = self._get_instrument_symbol(
                        'NIFTY',
                        new_expiry,
                        new_strike,
                        hedge['option_type']
                    )
                    quantity = LOT_SIZE if HEDGE_ONE_LOT else hedge['quantity']
                    
                    self.order_manager.place_order(
                        new_symbol,
                        quantity,
                        self.kite.TRANSACTION_TYPE_SELL
                    )
                    
                    new_hedges.append({
                        'tradingsymbol': new_symbol,
                        'expiry': new_expiry,
                        'strike': new_strike,
                        'quantity': quantity,
                        'option_type': hedge['option_type']
                    })
                    
                except Exception as e:
                    logger.error(f"Hedge rollover failed: {str(e)}")
                    new_hedges.append(hedge)  # Keep existing position
            else:
                new_hedges.append(hedge)
        
        self.current_hedges = new_hedges

    def _get_instrument_symbol(self, name, expiry, strike, option_type):
        """Find tradingsymbol for given parameters"""
        expiry_str = expiry.strftime('%Y-%m-%d')
        filtered = self.instruments[
            (self.instruments['name'] == name) &
            (self.instruments['expiry'] == expiry_str) &
            (self.instruments['strike'] == strike) &
            (self.instruments['instrument_type'] == option_type)
        ]
        
        if not filtered.empty:
            return filtered.iloc[0]['tradingsymbol']
        raise ValueError(f"Instrument {name} {expiry} {strike} {option_type} not found")

    def _get_safe_strike(self, expiry):
        """Get strike with minimum distance from spot"""
        base_strike = Helpers.get_nearest_strike(self.spot)
        candidates = sorted(
            self.instruments[
                (self.instruments['expiry'] == expiry.strftime('%Y-%m-%d')) &
                (self.instruments['name'] == 'NIFTY')
            ]['strike'].unique()
        )
        return min(candidates, key=lambda x: abs(x - (base_strike + self.min_strike_distance)))

    def calculate_premium_based_strike(self, expiry):
        """Find strike with premium below configured threshold"""
        instruments = self.instruments[
            (self.instruments['name'] == 'NIFTY') &
            (self.instruments['expiry'] == expiry.strftime('%Y-%m-%d'))
        ]
        
        for strike in sorted(instruments['strike'].unique()):
            symbol = self._get_instrument_symbol(
                'NIFTY',
                expiry,
                strike,
                'CE' if strike > self.spot else 'PE'
            )
            ltp = self.kite.ltp(f"NFO:{symbol}")[f"NFO:{symbol}"]['last_price']
            
            if ltp <= HEDGE_PREMIUM_THRESHOLD and \
               abs(strike - self.spot) >= self.min_strike_distance:
                return strike
                
        # Fallback to safest strike
        return self._get_safe_strike(expiry)

    def consolidate_quantities(self):
        """Merge duplicate hedge positions"""
        if HEDGE_ONE_LOT:
            logger.debug("Skipping consolidation in one-lot mode")
            return

        consolidated = {}
        for hedge in self.current_hedges:
            key = (hedge['expiry'], hedge['option_type'], hedge['strike'])
            if key in consolidated:
                consolidated[key]['quantity'] += hedge['quantity']
            else:
                consolidated[key] = hedge

        self.current_hedges = list(consolidated.values())

    def handle_far_month_adjustments(self):
        """Roll far month positions when nearing expiry"""
        current_far = self.current_far_expiry['far_month']
        new_far = self._get_initial_expiries()['far_month']
        
        if (new_far - current_far).days > 7:
            logger.info("Adjusting far month contracts")
            self._replace_far_month_hedges(new_far)

    def _replace_far_month_hedges(self, new_expiry):
        """Replace expiring far month positions"""
        for i, hedge in enumerate(self.current_hedges):
            if hedge['expiry'] == self.current_far_expiry['far_month']:
                try:
                    new_strike = self._get_adjusted_strike(new_expiry)
                    new_symbol = self._get_instrument_symbol(
                        'NIFTY',
                        new_expiry,
                        new_strike,
                        hedge['option_type']
                    )
                    
                    # Close old position
                    self.order_manager.place_order(
                        hedge['tradingsymbol'],
                        hedge['quantity'],
                        self.kite.TRANSACTION_TYPE_BUY
                    )
                    
                    # Open new position
                    self.order_manager.place_order(
                        new_symbol,
                        hedge['quantity'],
                        self.kite.TRANSACTION_TYPE_SELL
                    )
                    
                    # Update tracking
                    self.current_hedges[i].update({
                        'tradingsymbol': new_symbol,
                        'expiry': new_expiry,
                        'strike': new_strike
                    })
                    
                except Exception as e:
                    logger.error(f"Far month adjustment failed: {str(e)}")

    def _get_adjusted_strike(self, expiry):
        """Get strike based on configuration"""
        base_strike = Helpers.get_nearest_strike(self.spot)
        return base_strike + (ADJACENCY_GAP if FAR_SELL_ADD else 0)

    def get_hedge_instruments(self, spot_price: float, gap: int) -> List[Dict]:
        """Get hedge instruments based on spot price and adjacency gap"""
        weekly_expiry = self._get_nearest_expiry(weekly=True)
        instruments = []
        
        for opt_type in ['CE', 'PE']:
            strike = Helpers.get_nearest_strike(spot_price + (gap if opt_type == 'CE' else -gap))
            try:
                symbol = self._get_instrument_symbol('NIFTY', weekly_expiry, strike, opt_type)
                instruments.append({
                    'tradingsymbol': symbol,
                    'strike': strike,
                    'expiry': weekly_expiry,
                    'option_type': opt_type
                })
            except ValueError as e:
                logger.warning(f"Skipping invalid hedge instrument: {str(e)}")
        return instruments

    def get_instruments(self, strategy_type: str, ce_strike: float, pe_strike: float, far_sell_add: bool) -> List[Dict]:
        """Get tradingsymbols for strategy execution"""
        expiry = self._get_nearest_expiry(weekly=not far_sell_add)
        try:
            return [
                {
                    'tradingsymbol': self._get_instrument_symbol('NIFTY', expiry, ce_strike, 'CE'),
                    'lot_size': LOT_SIZE
                },
                {
                    'tradingsymbol': self._get_instrument_symbol('NIFTY', expiry, pe_strike, 'PE'),
                    'lot_size': LOT_SIZE
                }
            ]
        except ValueError as e:
            logger.error(f"Instrument lookup failed: {str(e)}")
            return []

    def daily_maintenance(self):
        """Execute daily maintenance tasks"""
        try:
            self.replace_expiring_hedges()
            self.consolidate_quantities()
            self.handle_far_month_adjustments()
            return True
        except Exception as e:
            logger.error(f"Daily maintenance failed: {str(e)}")
            return False

    def _get_nearest_expiry(self, weekly: bool = True) -> datetime:
        """Get nearest weekly or monthly expiry date"""
        expiries = sorted(self.instruments['expiry'].unique())
        valid_expiries = [datetime.strptime(e, '%Y-%m-%d') for e in expiries if e]
        future_expiries = [e for e in valid_expiries if e > datetime.now()]
        
        if weekly:
            return min([e for e in future_expiries if not self._is_monthly_expiry(e)])
        return [e for e in future_expiries if self._is_monthly_expiry(e)][min(3, len(future_expiries)-1)]

    def get_next_weekly_expiry(self, current_expiry: datetime) -> datetime:
        """Get next weekly expiry after current expiry"""
        weekly_expiries = self.get_weekly_expiries()
        try:
            return next(e for e in weekly_expiries if e > current_expiry)
        except StopIteration:
            return weekly_expiries[-1]
