# core/expiry_manager.py
import logging
from datetime import datetime, timedelta
import pandas as pd
from config import (
    ADJACENCY_GAP,
    FAR_SELL_ADD,
    HEDGE_ONE_LOT,
    LOT_SIZE,
    TRADE_DAYS
)
from utils.helpers import get_nearest_strike, get_premium

logger = logging.getLogger(__name__)

class ExpiryManager:
    def __init__(self, kite, order_manager, spot_price):
        self.kite = kite
        self.order_manager = order_manager
        self.spot = spot_price
        self.instruments = self._load_instruments()
        self.current_hedges = []
        self.current_far_expiry = self._get_initial_expiries()

    def _load_instruments(self):
        logger.info("Loading NFO instruments")
        return pd.DataFrame(self.kite.instruments("NFO"))

    def _get_initial_expiries(self):
        monthly_expiries = sorted([
            datetime.strptime(e, '%Y-%m-%d') 
            for e in self.instruments[self.instruments['name'] == 'NIFTY']['expiry'].unique()
            if e != ''
        ])
        return {
            'weekly': self.get_weekly_expiries()[0],
            'far_month': monthly_expiries[min(3, len(monthly_expiries)-1)]
        }

    def get_weekly_expiries(self):
        all_expiries = sorted(list(set(
            datetime.strptime(e, '%Y-%m-%d') 
            for e in self.instruments['expiry']
            if e != ''
        )))
        return [e for e in all_expiries if e.day <= 25]

    def get_next_weekly_expiry(self, current_expiry):
        weeklies = self.get_weekly_expiries()
        try:
            return next(e for e in weeklies if e > current_expiry)
        except StopIteration:
            logger.error("No next weekly expiry found")
            return current_expiry

    def needs_rollover(self, hedge):
        days_to_expiry = (hedge['expiry'] - datetime.now()).days
        return days_to_expiry <= 1 and hedge['expiry'].weekday() in TRADE_DAYS

    def replace_expiring_hedges(self):
        new_hedges = []
        for hedge in self.current_hedges:
            if self.needs_rollover(hedge):
                logger.info(f"Rolling over expiring hedge: {hedge['tradingsymbol']}")
                
                # Close existing position
                self.order_manager.place_order(
                    hedge['tradingsymbol'],
                    hedge['quantity'],
                    self.kite.TRANSACTION_TYPE_BUY
                )

                # Get new expiry and strike
                new_expiry = self.get_next_weekly_expiry(hedge['expiry'])
                new_strike = self.calculate_premium_based_strike(new_expiry)
                
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
                    'quantity': quantity,
                    'option_type': hedge['option_type']
                })
            else:
                new_hedges.append(hedge)
        
        self.current_hedges = new_hedges

    def _get_instrument_symbol(self, name, expiry, strike, option_type):
        expiry_str = expiry.strftime('%Y-%m-%d')
        instruments = self.instruments[
            (self.instruments['name'] == name) &
            (self.instruments['expiry'] == expiry_str) &
            (self.instruments['strike'] == strike) &
            (self.instruments['instrument_type'] == option_type)
        ]
        if not instruments.empty:
            return instruments.iloc[0]['tradingsymbol']
        raise ValueError(f"Instrument not found: {name} {expiry} {strike} {option_type}")

    def consolidate_quantities(self):
        if HEDGE_ONE_LOT:
            logger.info("Hedge consolidation skipped - one lot mode")
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
        current_far = self.current_far_expiry['far_month']
        new_far = self._get_initial_expiries()['far_month']
        
        if (new_far - current_far).days > 7:
            logger.info("Adjusting far month contracts")
            self._replace_far_month_hedges(new_far)

    def _replace_far_month_hedges(self, new_expiry):
        for i, hedge in enumerate(self.current_hedges):
            if hedge['expiry'] == self.current_far_expiry['far_month']:
                new_strike = self._get_adjusted_strike(new_expiry)
                new_symbol = self._get_instrument_symbol(
                    'NIFTY',
                    new_expiry,
                    new_strike,
                    hedge['option_type']
                )
                
                self.order_manager.place_order(
                    hedge['tradingsymbol'],
                    hedge['quantity'],
                    self.kite.TRANSACTION_TYPE_BUY
                )
                
                self.order_manager.place_order(
                    new_symbol,
                    hedge['quantity'],
                    self.kite.TRANSACTION_TYPE_SELL
                )
                
                self.current_hedges[i]['tradingsymbol'] = new_symbol
                self.current_hedges[i]['expiry'] = new_expiry
                self.current_hedges[i]['strike'] = new_strike

        self.current_far_expiry['far_month'] = new_expiry

    def _get_adjusted_strike(self, expiry):
        if FAR_SELL_ADD:
            return get_nearest_strike(self.spot + ADJACENCY_GAP)
        return get_nearest_strike(self.spot)

    def calculate_premium_based_strike(self, expiry):
        target_premium = 50  # Example threshold, should be config-driven
        strikes = sorted(set(self.instruments[
            (self.instruments['name'] == 'NIFTY') &
            (self.instruments['expiry'] == expiry.strftime('%Y-%m-%d'))
        ]['strike']))
        
        for strike in strikes:
            symbol = self._get_instrument_symbol(
                'NIFTY',
                expiry,
                strike,
                'CE' if strike > self.spot else 'PE'
            )
            if get_premium(self.kite, symbol) <= target_premium:
                return strike
        return strikes[len(strikes)//2]

    def daily_maintenance(self):
        try:
            self.replace_expiring_hedges()
            self.consolidate_quantities()
            self.handle_far_month_adjustments()
            return True
        except Exception as e:
            logger.error(f"Expiry maintenance failed: {str(e)}")
            return False
