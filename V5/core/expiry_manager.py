# core/expiry_manager.py
import logging
import calendar
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pandas as pd
from config import Config
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
        self.min_strike_distance = Config.ADJACENCY_GAP * 2
        self._validate_initial_setup()

    def _validate_initial_setup(self):
        if not self.current_far_expiry['far_month']:
            raise ValueError("No valid far month expiry found during initialization")

    def _load_instruments(self):
        logger.info("Loading NFO instruments")
        try:
            return pd.DataFrame(self.kite.instruments("NFO"))
        except Exception as e:
            logger.error(f"Failed to load instruments: {str(e)}")
            raise

    def _is_monthly_expiry(self, date_obj):
        last_thursday = max(
            week[3] 
            for week in calendar.monthcalendar(date_obj.year, date_obj.month)
            if week[3] != 0
        )
        return date_obj.day == last_thursday

    def _get_initial_expiries(self):
        try:
            all_expiries = sorted({
                datetime.strptime(e, '%Y-%m-%d') 
                for e in self.instruments[self.instruments['name'] == 'NIFTY']['expiry']
                if e != ''
            })
            
            monthly_expiries = [e for e in all_expiries if self._is_monthly_expiry(e)]
            if not monthly_expiries:
                raise ValueError("No monthly expiries available")

            weekly_expiries = [e for e in all_expiries if not self._is_monthly_expiry(e)]
            
            far_month = (
                monthly_expiries[Config.FAR_MONTH_INDEX] 
                if len(monthly_expiries) > Config.FAR_MONTH_INDEX
                else monthly_expiries[-1]
            )
            
            return {
                'weekly': weekly_expiries[0] if weekly_expiries else None,
                'far_month': far_month
            }
        except Exception as e:
            logger.error(f"Expiry initialization failed: {str(e)}")
            raise

    def get_weekly_expiries(self):
        return sorted([
            e for e in self._get_all_expiries()
            if not self._is_monthly_expiry(e)
        ])

    def _get_all_expiries(self):
        try:
            return sorted({
                datetime.strptime(e, '%Y-%m-%d')
                for e in self.instruments['expiry']
                if e != ''
            })
        except Exception as e:
            logger.error(f"Expiry extraction failed: {str(e)}")
            return []

    def needs_rollover(self, hedge):
        if not hedge:
            return False
            
        days_to_expiry = (hedge['expiry'] - datetime.now()).days
        return days_to_expiry <= Config.ROLLOVER_DAYS_THRESHOLD

    def replace_expiring_hedges(self):
        new_hedges = []
        for hedge in self.current_hedges:
            if not self.needs_rollover(hedge):
                new_hedges.append(hedge)
                continue

            logger.info(f"Rolling over hedge: {hedge['tradingsymbol']}")
            try:
                # Determine close transaction type
                close_type = (self.kite.TRANSACTION_TYPE_SELL 
                            if hedge['transaction_type'] == self.kite.TRANSACTION_TYPE_BUY 
                            else self.kite.TRANSACTION_TYPE_BUY)

                # Close existing position
                close_order = self.order_manager.place_order(
                    hedge['tradingsymbol'],
                    abs(hedge['quantity']),
                    close_type
                )
                
                if not self._verify_order_completion(close_order):
                    raise Exception("Hedge close order failed")

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
                quantity = Config.LOT_SIZE if Config.HEDGE_ONE_LOT else hedge['quantity']
                
                place_order = self.order_manager.place_order(
                    new_symbol,
                    quantity,
                    hedge['transaction_type']  # Maintain original direction
                )
                
                if not self._verify_order_completion(place_order):
                    raise Exception("Hedge placement failed")

                new_hedges.append({
                    'tradingsymbol': new_symbol,
                    'expiry': new_expiry,
                    'strike': new_strike,
                    'quantity': quantity,
                    'option_type': hedge['option_type'],
                    'transaction_type': hedge['transaction_type'],
                    'order_id': place_order
                })
                
            except Exception as e:
                logger.error(f"Hedge rollover failed: {str(e)} - Keeping original hedge")
                new_hedges.append(hedge)

        self.current_hedges = new_hedges

    def _verify_order_completion(self, order_id):
        try:
            orders = self.kite.orders()
            return any(order['order_id'] == order_id 
                      and order['status'] == 'COMPLETE' 
                      for order in orders)
        except Exception as e:
            logger.error(f"Order verification failed: {str(e)}")
            return False

    def _get_instrument_symbol(self, name, expiry, strike, option_type):
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
        base_strike = Helpers.get_nearest_strike(self.spot)
        candidates = sorted(
            self.instruments[
                (self.instruments['expiry'] == expiry.strftime('%Y-%m-%d')) &
                (self.instruments['name'] == 'NIFTY')
            ]['strike'].unique()
        )
        return min(candidates, key=lambda x: abs(x - (base_strike + self.min_strike_distance)))

    def calculate_premium_based_strike(self, expiry):
        instruments = self.instruments[
            (self.instruments['name'] == 'NIFTY') &
            (self.instruments['expiry'] == expiry.strftime('%Y-%m-%d'))
        ]
        
        for strike in sorted(instruments['strike'].unique()):
            try:
                symbol = self._get_instrument_symbol(
                    'NIFTY',
                    expiry,
                    strike,
                    'CE' if strike > self.spot else 'PE'
                )
                ltp = self.kite.ltp(f"NFO:{symbol}")[f"NFO:{symbol}"]['last_price']
                
                if (ltp <= Config.HEDGE_PREMIUM_THRESHOLD and 
                    abs(strike - self.spot) >= self.min_strike_distance):
                    return strike
            except Exception as e:
                logger.warning(f"Skipping strike {strike}: {str(e)}")
                continue
                
        return self._get_safe_strike(expiry)

    def consolidate_quantities(self):
        if Config.HEDGE_ONE_LOT:
            logger.debug("Skipping consolidation in one-lot mode")
            return

        consolidated = {}
        for hedge in self.current_hedges:
            key = (hedge['expiry'], hedge['option_type'], hedge['strike'], hedge['transaction_type'])
            if key in consolidated:
                consolidated[key]['quantity'] += hedge['quantity']
            else:
                consolidated[key] = hedge

        self.current_hedges = list(consolidated.values())

    def handle_far_month_adjustments(self):
        current_far = self.current_far_expiry['far_month']
        new_far = self._get_initial_expiries()['far_month']
        
        if (new_far - current_far).days > 7:
            logger.info("Adjusting far month contracts")
            self._replace_far_month_hedges(new_far)

    def _replace_far_month_hedges(self, new_expiry):
        for i, hedge in enumerate(self.current_hedges):
            if hedge['expiry'] != self.current_far_expiry['far_month']:
                continue

            try:
                new_strike = self._get_adjusted_strike(new_expiry)
                new_symbol = self._get_instrument_symbol(
                    'NIFTY',
                    new_expiry,
                    new_strike,
                    hedge['option_type']
                )
                
                # Close old position
                close_type = (self.kite.TRANSACTION_TYPE_SELL 
                            if hedge['transaction_type'] == self.kite.TRANSACTION_TYPE_BUY 
                            else self.kite.TRANSACTION_TYPE_BUY)
                
                close_order = self.order_manager.place_order(
                    hedge['tradingsymbol'],
                    abs(hedge['quantity']),
                    close_type
                )
                
                if not self._verify_order_completion(close_order):
                    raise Exception("Far month close order failed")

                # Open new position
                place_order = self.order_manager.place_order(
                    new_symbol,
                    hedge['quantity'],
                    hedge['transaction_type']
                )
                
                if not self._verify_order_completion(place_order):
                    raise Exception("Far month placement failed")

                # Update tracking
                self.current_hedges[i].update({
                    'tradingsymbol': new_symbol,
                    'expiry': new_expiry,
                    'strike': new_strike
                })
                
            except Exception as e:
                logger.error(f"Far month adjustment failed: {str(e)}")
                continue

    def _get_adjusted_strike(self, expiry):
        base_strike = Helpers.get_nearest_strike(self.spot)
        return base_strike + (Config.ADJACENCY_GAP if Config.FAR_SELL_ADD else 0)

    def get_hedge_instruments(self, spot_price: float, gap: int) -> List[Dict]:
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
                    'option_type': opt_type,
                    'transaction_type': self.kite.TRANSACTION_TYPE_BUY
                })
            except ValueError as e:
                logger.warning(f"Skipping invalid hedge instrument: {str(e)}")
        return instruments

    def get_instruments(self, strategy_type: str, ce_strike: float, pe_strike: float, far_sell_add: bool) -> List[Dict]:
        expiry = self._get_nearest_expiry(weekly=not far_sell_add)
        try:
            return [
                {
                    'tradingsymbol': self._get_instrument_symbol('NIFTY', expiry, ce_strike, 'CE'),
                    'strike': ce_strike,
                    'expiry': expiry,
                    'lot_size': Config.LOT_SIZE,
                    'transaction_type': self.kite.TRANSACTION_TYPE_SELL
                },
                {
                    'tradingsymbol': self._get_instrument_symbol('NIFTY', expiry, pe_strike, 'PE'),
                    'strike': pe_strike,
                    'expiry': expiry,
                    'lot_size': Config.LOT_SIZE,
                    'transaction_type': self.kite.TRANSACTION_TYPE_SELL
                }
            ]
        except ValueError as e:
            logger.error(f"Instrument lookup failed: {str(e)}")
            return []

    def daily_maintenance(self):
        try:
            self.replace_expiring_hedges()
            self.consolidate_quantities()
            self.handle_far_month_adjustments()
            return True
        except Exception as e:
            logger.error(f"Daily maintenance failed: {str(e)}")
            return False

    def _get_nearest_expiry(self, weekly: bool = True) -> datetime:
        try:
            expiries = sorted(self.instruments['expiry'].unique())
            valid_expiries = [datetime.strptime(e, '%Y-%m-%d') for e in expiries if e]
            future_expiries = [e for e in valid_expiries if e > datetime.now()]
            
            if weekly:
                return min([e for e in future_expiries if not self._is_monthly_expiry(e)])
            monthly = [e for e in future_expiries if self._is_monthly_expiry(e)]
            return monthly[min(Config.FAR_MONTH_INDEX, len(monthly)-1)]
        except Exception as e:
            logger.error(f"Expiry lookup failed: {str(e)}")
            raise

    def get_next_weekly_expiry(self, current_expiry: datetime) -> datetime:
        weekly_expiries = self.get_weekly_expiries()
        try:
            return next(e for e in weekly_expiries if e > current_expiry)
        except StopIteration:
            logger.warning("No future weekly expiries found")
            return current_expiry
