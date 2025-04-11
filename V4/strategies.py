%%writefile strategies.py
import datetime
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
from logger import setup_logger

log = setup_logger()

class OptionStrategy:
    def __init__(self, 
                 position_manager: Optional[PositionManager] = None,
                 order_manager: Optional[OrderManager] = None,
                 instrument_manager: Optional[InstrumentManager] = None):
        """Initialize strategy with dependencies"""
        log.info("Initializing OptionStrategy")
        self.position_manager = position_manager or PositionManager()
        self.order_manager = order_manager or OrderManager()
        self.instrument_manager = instrument_manager or InstrumentManager()
        self.spot_price = self.instrument_manager.get_spot_price()
        log.debug(f"Strategy initialized with spot price: {self.spot_price}")

    def manage_strategy(self) -> None:
        """Main strategy execution method"""
        log.info("Starting strategy management cycle")
        if not is_market_open():
            log.info("Market closed - skipping execution")
            return

        try:
            log.debug("Syncing positions")
            self.position_manager.sync_positions()
            
            if self.check_shutdown_condition():
                log.warning("Shutdown condition triggered - closing all positions")
                self.close_all_positions()
                return

            if config.STRADDLE_FLAG:
                log.info("Straddle flag enabled - managing straddle")
                self.manage_straddle()
            elif config.STRANGLE_FLAG:
                log.info("Strangle flag enabled - managing strangle")
                self.manage_strangle()

            log.debug("Managing hedges and profit booking")
            self.manage_hedges()
            self.manage_profit_booking()
            self.manage_expiry_rollover()
            
            log.debug("Checking profit targets")
            self.check_profit_targets()

        except Exception as e:
            log.error("Strategy execution failed", exc_info=True)
        finally:
            log.info("Strategy management cycle completed")

    def check_shutdown_condition(self) -> bool:
        """Check if shutdown threshold is breached"""
        log.debug("Checking shutdown condition")
        unrealized_pnl = self.position_manager.calculate_unrealized_pnl()
        margin = self.position_manager.kite.margins()['equity']['available']['cash']
        threshold = abs(margin * config.SHUTDOWN_LOSS)
        result = unrealized_pnl <= -threshold
        log.info(f"Shutdown check: PNL={unrealized_pnl}, Threshold={threshold}, Result={result}")
        return result

    def manage_straddle(self) -> None:
        """Implement short straddle strategy"""
        log.info("Managing straddle positions")
        active_positions = self.position_manager.get_active_positions('straddle')
        if active_positions:
            log.info(f"Found {len(active_positions)} active straddle positions - skipping new entry")
            return

        expiry_date = get_expiry_date('monthly')
        strike = round_strike(self.spot_price + config.BIAS)
        log.debug(f"Calculated straddle strike: {strike} for expiry: {expiry_date}")

        ce_instruments = filter_instruments(
            self.instrument_manager.nifty_instruments,
            expiry_date,
            'CE',
            strike
        )
        pe_instruments = filter_instruments(
            self.instrument_manager.nifty_instruments,
            expiry_date,
            'PE',
            strike
        )

        if not ce_instruments or not pe_instruments:
            log.error("Missing instruments for straddle")
            return

        margin = self.position_manager.kite.margins()['equity']['available']['cash']
        qty = calculate_quantity(margin, 0)  # volatility=0 for basic calculation
        log.debug(f"Straddle quantity: {qty}")

        try:
            log.info(f"Placing straddle orders at {strike}")
            ce_order = self.order_manager.place_order(
                'SELL', 
                ce_instruments[0], 
                qty, 
                'MARKET', 
                tag='STRADDLE_CE'
            )
            pe_order = self.order_manager.place_order(
                'SELL', 
                pe_instruments[0], 
                qty, 
                'MARKET', 
                tag='STRADDLE_PE'
            )
            log.info(f"Straddle entered - CE Order: {ce_order}, PE Order: {pe_order}")
        except Exception as e:
            log.error("Straddle entry failed", exc_info=True)

    def manage_strangle(self) -> None:
        """Implement short strangle strategy"""
        log.info("Managing strangle positions")
        active_positions = self.position_manager.get_active_positions('strangle')
        if active_positions:
            log.info(f"Found {len(active_positions)} active strangle positions - skipping new entry")
            return

        expiry_date = get_expiry_date('monthly')
        ce_strike = round_strike(self.spot_price + config.STRANGLE_DISTANCE)
        pe_strike = round_strike(self.spot_price - config.STRANGLE_DISTANCE)
        log.debug(f"Calculated strangle strikes: CE={ce_strike}, PE={pe_strike}")

        ce_instruments = filter_instruments(
            self.instrument_manager.nifty_instruments,
            expiry_date,
            'CE',
            ce_strike
        )
        pe_instruments = filter_instruments(
            self.instrument_manager.nifty_instruments,
            expiry_date,
            'PE',
            pe_strike
        )

        margin = self.position_manager.kite.margins()['equity']['available']['cash']
        qty = calculate_quantity(margin, 0)
        log.debug(f"Strangle quantity: {qty}")

        try:
            log.info(f"Placing strangle orders at CE:{ce_strike}, PE:{pe_strike}")
            ce_order = self.order_manager.place_order(
                'SELL', 
                ce_instruments[0], 
                qty, 
                'MARKET', 
                tag='STRANGLE_CE'
            )
            pe_order = self.order_manager.place_order(
                'SELL', 
                pe_instruments[0], 
                qty, 
                'MARKET', 
                tag='STRANGLE_PE'
            )
            log.info(f"Strangle entered - CE Order: {ce_order}, PE Order: {pe_order}")
        except Exception as e:
            log.error("Strangle entry failed", exc_info=True)

    def manage_hedges(self) -> None:
        """Manage hedge positions based on P&L thresholds"""
        log.info("Managing hedge positions")
        for position in list(self.position_manager.positions.get('net', [])):
            if position['quantity'] >= 0 or position['product'] != 'MIS':
                continue

            entry_price = abs(position['average_price'])
            current_price = abs(position['last_price'])
            pnl_pct = (current_price - entry_price) / entry_price
            log.debug(f"Position {position['tradingsymbol']} PnL%: {pnl_pct:.2%}")

            if pnl_pct <= -config.HEDGE_LOSS_THRESHOLD and config.BUY_HEDGE:
                log.info(f"Hedge triggered for {position['tradingsymbol']}")
                strike = position['strike']
                expiry = position['expiry']
                option_type = position['instrument_type']
                new_strike = strike - config.ADJACENCY_GAP if option_type == 'PE' else strike + config.ADJACENCY_GAP
                log.debug(f"New hedge strike: {new_strike}")

                if self.position_manager.existing_position_check(expiry, new_strike, option_type):
                    log.info(f"Existing hedge at {new_strike} - skipping")
                    continue

                instruments = filter_instruments(
                    self.instrument_manager.nifty_instruments,
                    expiry,
                    option_type,
                    new_strike
                )
                if instruments:
                    try:
                        hedge_order = self.order_manager.place_order(
                            'SELL', 
                            instruments[0], 
                            position['quantity'], 
                            'MARKET', 
                            tag='HEDGE'
                        )
                        log.info(f"Hedge order placed: {hedge_order}")
                    except Exception as e:
                        log.error("Hedge placement failed", exc_info=True)

    def manage_profit_booking(self) -> None:
        """Manage profit booking and stop loss updates"""
        log.info("Managing profit booking")
        for position in self.position_manager.positions.get('net', []):
            if position['quantity'] >= 0:
                continue

            entry_price = abs(position['average_price'])
            current_price = abs(position['last_price'])
            profit_pct = (entry_price - current_price) / entry_price
            log.debug(f"Position {position['tradingsymbol']} Profit%: {profit_pct:.2%}")

            if profit_pct >= config.PROFIT_THRESHOLD:
                sl_price = entry_price * (1 - config.STOPLOSS_THRESHOLD * profit_pct)
                log.info(f"Updating SL for {position['tradingsymbol']} to {sl_price:.2f}")
                try:
                    modified_id = self.order_manager.modify_order(position['order_id'], sl_price)
                    log.info(f"SL updated - Order ID: {modified_id}")
                except Exception as e:
                    log.error("SL update failed", exc_info=True)

                new_expiry = get_expiry_date('monthly' if config.FAR_SELL_ADD else 'weekly')
                instruments = filter_instruments(
                    self.instrument_manager.nifty_instruments,
                    new_expiry,
                    position['instrument_type'],
                    position['strike']
                )
                if instruments:
                    try:
                        profit_order = self.order_manager.place_order(
                            'SELL', 
                            instruments[0], 
                            position['quantity'], 
                            'MARKET', 
                            tag='PROFIT_ADD'
                        )
                        log.info(f"Profit booking order placed: {profit_order}")
                    except Exception as e:
                        log.error("Profit booking failed", exc_info=True)

    def manage_expiry_rollover(self) -> None:
        """Handle position rollover near expiry"""
        log.info("Managing expiry rollover")
        now = datetime.datetime.now()
        for position in self.position_manager.positions.get('net', []):
            expiry_date = datetime.datetime.strptime(position['expiry'], '%Y-%m-%d').date()
            if (expiry_date - now.date()).days > 3 or position['quantity'] == 0:
                continue

            log.info(f"Rolling over expiring position: {position['tradingsymbol']}")
            try:
                instrument = self.instrument_manager.get_instrument(position['instrument_token'])
                close_order = self.order_manager.place_order(
                    'BUY' if position['quantity'] < 0 else 'SELL',
                    instrument,
                    abs(position['quantity']),
                    'MARKET',
                    tag='ROLLOVER_CLOSE'
                )
                log.info(f"Closed expiring position - Order ID: {close_order}")

                new_expiry = get_expiry_date('monthly' if position['tag'] in ['STRADDLE','STRANGLE'] else 'weekly')
                new_strike = round_strike(position['strike'] + (position['average_price'] * 0.5))
                log.debug(f"New rollover strike: {new_strike}, expiry: {new_expiry}")

                instruments = filter_instruments(
                    self.instrument_manager.nifty_instruments,
                    new_expiry,
                    position['instrument_type'],
                    new_strike
                )
                if instruments:
                    qty = position['quantity'] * 2 if 'HEDGE' in position['tag'] else position['quantity']
                    rollover_order = self.order_manager.place_order(
                        'SELL' if qty < 0 else 'BUY',
                        instruments[0],
                        abs(qty),
                        'MARKET',
                        tag=f"{position['tag']}_ROLLOVER"
                    )
                    log.info(f"Rollover order placed: {rollover_order}")
            except Exception as e:
                log.error("Rollover failed", exc_info=True)

    def check_profit_targets(self) -> bool:
        """Check if profit target is reached"""
        log.info("Checking profit targets")
        net_profit = self.position_manager.calculate_unrealized_pnl()
        target = calculate_profit_points(config.PROFIT_POINTS)
        log.debug(f"Current P&L: {net_profit}, Target: {target}")

        if net_profit >= target:
            log.info(f"Profit target reached ({net_profit} >= {target}) - closing positions")
            self.close_all_positions()
            return True
        return False

    def get_active_buy_qty(self, option_type: str) -> int:
        """Get total active buy quantity for option type"""
        log.debug(f"Getting active buy quantity for {option_type}")
        result = sum(
            p['quantity'] for p in self.position_manager.positions.get('net', [])
            if p['instrument_type'] == option_type and p['quantity'] > 0
        )
        log.debug(f"Active buy quantity: {result}")
        return result

    def close_all_positions(self) -> None:
        """Close all active positions"""
        log.warning("Initiating full position closure")
        for position in self.position_manager.positions.get('net', []):
            if position['quantity'] == 0:
                continue

            instrument = self.instrument_manager.get_instrument(position['instrument_token'])
            if not instrument:
                log.error(f"No instrument found for token: {position['instrument_token']}")
                continue

            try:
                close_order = self.order_manager.place_order(
                    'BUY' if position['quantity'] < 0 else 'SELL',
                    instrument,
                    abs(position['quantity']),
                    'MARKET',
                    tag='SHUTDOWN_CLOSE'
                )
                log.info(f"Closed position {position['tradingsymbol']} - Order ID: {close_order}")
            except Exception as e:
                log.error(f"Position closure failed for {position['tradingsymbol']}", exc_info=True)
