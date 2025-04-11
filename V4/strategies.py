%%writefile strategies.py
import datetime
import logging
from typing import Optional, Dict, List
from config import config
from positions import PositionManager
from orders import OrderManager
from instruments import InstrumentManager
from utils import (
    is_market_open,
    get_expiry_date,
    filter_instruments,
    calculate_quantity,
    round_strike,
    calculate_profit_points
)
from logger import get_logger

log = get_logger()

class OptionStrategy:
    """Main class implementing short straddle/strangle strategy with hedging and risk management"""

    def __init__(self, 
                 position_manager: Optional[PositionManager] = None,
                 order_manager: Optional[OrderManager] = None,
                 instrument_manager: Optional[InstrumentManager] = None):
        """Initialize strategy components"""
        self.position_manager = position_manager or PositionManager()
        self.order_manager = order_manager or OrderManager()
        self.instrument_manager = instrument_manager or InstrumentManager()
        self.spot_price = self.instrument_manager.get_spot_price()
        self.active_orders = []

    def manage_strategy(self) -> None:
        """Main strategy execution loop"""
        if not self._should_run():
            return

        try:
            self.position_manager.sync_positions()
            
            if self.check_shutdown_condition():
                self.close_all_positions()
                return

            if config.STRADDLE_FLAG:
                self.manage_straddle()
            elif config.STRANGLE_FLAG:
                self.manage_strangle()

            self.manage_hedges()
            self.manage_profit_booking()
            self.manage_expiry_rollover()
            self.check_profit_targets()

        except Exception as e:
            log.error("Strategy execution failed", exc_info=True)

    def _should_run(self) -> bool:
        """Check market timings and special conditions"""
        if not is_market_open():
            log.info("Market closed - skipping execution")
            return False
        if datetime.datetime.now().date().strftime("%Y-%m-%d") in config.HOLIDAYS:
            log.info("Holiday - skipping execution")
            return False
        return True

    def manage_straddle(self) -> None:
        """Implement short straddle strategy"""
        if self._has_active_positions('straddle'):
            return

        expiry = get_expiry_date('monthly', datetime.date.today() + datetime.timedelta(days=30*config.EXPIRY_MONTHS))
        strike = round_strike(self.spot_price + config.BIAS)

        ce_instruments = self._get_valid_instruments(expiry, 'CE', strike)
        pe_instruments = self._get_valid_instruments(expiry, 'PE', strike)

        if not ce_instruments or not pe_instruments:
            return

        qty = self._calculate_safe_quantity()
        self._place_strategy_orders(ce_instruments[0], pe_instruments[0], qty, 'STRADDLE')

    def manage_strangle(self) -> None:
        """Implement short strangle strategy"""
        if self._has_active_positions('strangle'):
            return

        expiry = get_expiry_date('monthly', datetime.date.today() + datetime.timedelta(days=30*config.EXPIRY_MONTHS))
        ce_strike = round_strike(self.spot_price + config.STRANGLE_DISTANCE)
        pe_strike = round_strike(self.spot_price - config.STRANGLE_DISTANCE)

        ce_instruments = self._get_valid_instruments(expiry, 'CE', ce_strike)
        pe_instruments = self._get_valid_instruments(expiry, 'PE', pe_strike)

        qty = self._calculate_safe_quantity()
        self._place_strategy_orders(ce_instruments[0], pe_instruments[0], qty, 'STRANGLE')

    def manage_hedges(self) -> None:
        """Manage hedge positions and replacements"""
        for position in list(self.position_manager.positions.get('net', [])):
            if position['quantity'] > 0:  # Buy positions
                self._manage_buy_hedges(position)
            elif position['quantity'] < 0:  # Sell positions
                self._manage_sell_hedges(position)

    def _manage_buy_hedges(self, position: Dict) -> None:
        """Handle buy position hedging"""
        entry_price = position['average_price']
        current_price = position['last_price']
        pnl_pct = (current_price - entry_price) / entry_price

        # Check for 25% loss
        if pnl_pct <= -config.HEDGE_LOSS_THRESHOLD and config.BUY_HEDGE:
            self._place_hedge_order(position)

        # Check spot price proximity
        if abs(self.spot_price - position['strike']) < config.HEDGE_CLOSING_BUFFER:
            self._replace_hedge_with_far_month(position)

    def _place_hedge_order(self, position: Dict) -> None:
        """Place adjacent hedge order"""
        new_strike = position['strike'] - config.ADJACENCY_GAP if position['instrument_type'] == 'PE' \
            else position['strike'] + config.ADJACENCY_GAP

        instruments = filter_instruments(
            self.instrument_manager.nifty_instruments,
            position['expiry'],
            position['instrument_type'],
            new_strike,
            recursive=True
        )

        if instruments and not self.position_manager.existing_position_check(
            position['expiry'], new_strike, position['instrument_type']
        ):
            try:
                self.order_manager.place_order(
                    'SELL',
                    instruments[0],
                    position['quantity'],
                    'MARKET',
                    tag=f"HEDGE_{position['instrument_type']}"
                )
            except Exception as e:
                log.error("Hedge placement failed", exc_info=True)

    def _replace_hedge_with_far_month(self, position: Dict) -> None:
        """Close current hedge and create far month position"""
        try:
            # Close existing hedge
            self.order_manager.place_order(
                'SELL' if position['quantity'] > 0 else 'BUY',
                self.instrument_manager.get_instrument(position['instrument_token']),
                abs(position['quantity']),
                'MARKET',
                tag='HEDGE_CLOSE'
            )

            # Calculate new parameters
            new_strike = round_strike(position['average_price'] / 2)
            expiry = get_expiry_date('monthly', datetime.date.today() + datetime.timedelta(days=30*2))
            
            # Place new far month order
            instruments = filter_instruments(
                self.instrument_manager.nifty_instruments,
                expiry,
                position['instrument_type'],
                new_strike
            )
            if instruments:
                self.order_manager.place_order(
                    'SELL',
                    instruments[0],
                    position['quantity'] * 2,
                    'MARKET',
                    tag='FAR_HEDGE'
                )
        except Exception as e:
            log.error("Hedge replacement failed", exc_info=True)

    def manage_profit_booking(self) -> None:
        """Manage profit booking and stop loss updates"""
        for position in self.position_manager.positions.get('net', []):
            if position['quantity'] >= 0:
                continue

            entry_price = abs(position['average_price'])
            current_price = abs(position['last_price'])
            profit_pct = (entry_price - current_price) / entry_price

            if profit_pct >= config.PROFIT_THRESHOLD:
                self._update_stop_loss(position)
                self._add_profit_order(position)

    def _update_stop_loss(self, position: Dict) -> None:
        """Update stop loss to 90% of profit level"""
        try:
            sl_price = position['average_price'] * (1 - config.STOPLOSS_THRESHOLD)
            self.order_manager.modify_order(position['order_id'], sl_price)
        except Exception as e:
            log.error("SL update failed", exc_info=True)

    def _add_profit_order(self, position: Dict) -> None:
        """Add new sell order on profit hit"""
        expiry = get_expiry_date('monthly' if config.FAR_SELL_ADD else 'weekly')
        instruments = filter_instruments(
            self.instrument_manager.nifty_instruments,
            expiry,
            position['instrument_type'],
            position['strike'],
            recursive=True
        )
        if instruments:
            try:
                self.order_manager.place_order(
                    'SELL',
                    instruments[0],
                    position['quantity'],
                    'MARKET',
                    tag='PROFIT_ADD'
                )
            except Exception as e:
                log.error("Profit booking failed", exc_info=True)

    def manage_expiry_rollover(self) -> None:
        """Handle position rollover near expiry"""
        for position in self.position_manager.positions.get('net', []):
            if position['quantity'] == 0:
                continue

            expiry_date = datetime.datetime.strptime(position['expiry'], '%Y-%m-%d').date()
            days_to_expiry = (expiry_date - datetime.date.today()).days

            if days_to_expiry <= 1:
                self._roll_position(position)

    def _roll_position(self, position: Dict) -> None:
        """Roll expiring position to new expiry"""
        try:
            # Close expiring position
            self.order_manager.place_order(
                'BUY' if position['quantity'] < 0 else 'SELL',
                self.instrument_manager.get_instrument(position['instrument_token']),
                abs(position['quantity']),
                'MARKET',
                tag='ROLLOVER_CLOSE'
            )

            # Determine new expiry and strike
            new_expiry = get_expiry_date('monthly' if 'STRADDLE' in position['tag'] else 'weekly')
            new_strike = round_strike(position['strike'] + (position['average_price'] * 0.5))

            # Place new position
            instruments = filter_instruments(
                self.instrument_manager.nifty_instruments,
                new_expiry,
                position['instrument_type'],
                new_strike,
                recursive=True
            )
            if instruments:
                self.order_manager.place_order(
                    'SELL' if position['quantity'] < 0 else 'BUY',
                    instruments[0],
                    abs(position['quantity']),
                    'MARKET',
                    tag=f"{position['tag']}_ROLLOVER"
                )
        except Exception as e:
            log.error("Position rollover failed", exc_info=True)

    def check_profit_targets(self) -> bool:
        """Check if profit target is reached"""
        net_profit = self.position_manager.calculate_unrealized_pnl()
        if net_profit >= config.PROFIT_POINTS * config.POINT_VALUE:
            self.close_all_positions()
            return True
        return False

    def check_shutdown_condition(self) -> bool:
        """Check if unrealized loss exceeds threshold"""
        unrealized_pnl = self.position_manager.calculate_unrealized_pnl()
        margin = self.position_manager.kite.margins()['equity']['available']['cash']
        return unrealized_pnl <= -abs(margin * config.SHUTDOWN_LOSS)

    def close_all_positions(self) -> None:
        """Close all active positions"""
        for position in self.position_manager.positions.get('net', []):
            if position['quantity'] == 0:
                continue

            try:
                self.order_manager.place_order(
                    'BUY' if position['quantity'] < 0 else 'SELL',
                    self.instrument_manager.get_instrument(position['instrument_token']),
                    abs(position['quantity']),
                    'MARKET',
                    tag='SHUTDOWN_CLOSE'
                )
            except Exception as e:
                log.error(f"Position closure failed: {position['tradingsymbol']}", exc_info=True)

    def _has_active_positions(self, strategy_type: str) -> bool:
        """Check for existing active positions"""
        return len(self.position_manager.get_active_positions(strategy_type)) > 0

    def _get_valid_instruments(self, expiry: datetime.date, option_type: str, strike: float) -> List:
        """Get instruments with conflict check"""
        instruments = filter_instruments(
            self.instrument_manager.nifty_instruments,
            expiry,
            option_type,
            strike,
            recursive=True
        )
        while instruments and self.position_manager.existing_position_check(expiry, strike, option_type):
            strike -= config.STRIKE_ROUNDING
            instruments = filter_instruments(
                self.instrument_manager.nifty_instruments,
                expiry,
                option_type,
                strike,
                recursive=True
            )
        return instruments

    def _calculate_safe_quantity(self) -> int:
        """Calculate quantity with margin safety"""
        margin = self.position_manager.kite.margins()['equity']['available']['cash']
        return calculate_quantity(margin, volatility=0)

    def _place_strategy_orders(self, ce_instrument: Dict, pe_instrument: Dict, qty: int, tag: str) -> None:
        """Place strategy orders with conflict checking"""
        try:
            self.order_manager.place_order('SELL', ce_instrument, qty, 'MARKET', tag=f"{tag}_CE")
            self.order_manager.place_order('SELL', pe_instrument, qty, 'MARKET', tag=f"{tag}_PE")
        except Exception as e:
            log.error(f"{tag} entry failed", exc_info=True)
            # Fallback to limit orders
            try:
                self.order_manager.place_order('SELL', ce_instrument, qty, 'LIMIT')
                self.order_manager.place_order('SELL', pe_instrument, qty, 'LIMIT')
            except Exception as e:
                log.error(f"{tag} limit order fallback failed", exc_info=True)
