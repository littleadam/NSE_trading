%%writefile strategies.py
import datetime
import logging
from positions import PositionManager
from orders import OrderManager
from instruments import InstrumentManager
from utils import is_market_open, get_expiry_date, filter_instruments, calculate_quantity
from config import *
import math

class OptionStrategy:
    def __init__(self):
        self.position_manager = PositionManager()
        self.order_manager = OrderManager()
        self.instrument_manager = InstrumentManager()
        self.spot_price = self.instrument_manager.get_spot_price()
        self.log = logging.getLogger(__name__)

    def manage_strategy(self):
        if not is_market_open():
            self.log.info("Market closed. Skipping strategy execution.")
            return

        try:
            self.position_manager.sync_positions()
            
            if self.check_shutdown_condition():
                self.log.warning("Shutdown condition triggered. Closing all positions.")
                self.close_all_positions()
                return

            if STRADDLE_FLAG:
                self.manage_straddle()
            elif STRANGLE_FLAG:
                self.manage_strangle()

            self.manage_hedges()
            self.manage_profit_booking()
            self.manage_expiry_rollover()
            self.check_profit_targets()

        except Exception as e:
            self.log.error(f"Strategy execution failed: {str(e)}", exc_info=True)

    def check_shutdown_condition(self):
        unrealized_pnl = self.position_manager.calculate_unrealized_pnl()
        margin = self.position_manager.kite.margins()['equity']['available']['cash']
        return unrealized_pnl <= -abs(margin * SHUTDOWN_LOSS)

    def manage_straddle(self):
        active_positions = self.position_manager.get_active_positions('straddle')
        if active_positions:
            self.log.info("Active straddle positions exist. Skipping new entry.")
            return

        expiry_date = get_expiry_date('monthly', datetime.date.today() + datetime.timedelta(days=30*EXPIRY_MONTHS))
        strike = round((self.spot_price + BIAS)/50)*50

        ce_instruments = filter_instruments(self.instrument_manager.nifty_instruments, 
                                          expiry_date, 'CE', strike)
        pe_instruments = filter_instruments(self.instrument_manager.nifty_instruments,
                                          expiry_date, 'PE', strike)

        if not ce_instruments or not pe_instruments:
            self.log.error("Missing instruments for straddle")
            return

        margin = self.position_manager.kite.margins()['equity']['available']['cash']
        qty = calculate_quantity(margin, 0)

        try:
            self.order_manager.place_order('SELL', ce_instruments[0], qty, 'MARKET', tag='STRADDLE_CE')
            self.order_manager.place_order('SELL', pe_instruments[0], qty, 'MARKET', tag='STRADDLE_PE')
            self.log.info(f"Straddle entry at {strike} for {expiry_date}")
        except Exception as e:
            self.log.error(f"Straddle entry failed: {str(e)}")

    def manage_strangle(self):
        active_positions = self.position_manager.get_active_positions('strangle')
        if active_positions:
            self.log.info("Active strangle positions exist. Skipping new entry.")
            return

        expiry_date = get_expiry_date('monthly', datetime.date.today() + datetime.timedelta(days=30*EXPIRY_MONTHS))
        ce_strike = round((self.spot_price + STRANGLE_DISTANCE)/50)*50
        pe_strike = round((self.spot_price - STRANGLE_DISTANCE)/50)*50

        ce_instruments = filter_instruments(self.instrument_manager.nifty_instruments,
                                          expiry_date, 'CE', ce_strike)
        pe_instruments = filter_instruments(self.instrument_manager.nifty_instruments,
                                          expiry_date, 'PE', pe_strike)

        margin = self.position_manager.kite.margins()['equity']['available']['cash']
        qty = calculate_quantity(margin, 0)

        try:
            self.order_manager.place_order('SELL', ce_instruments[0], qty, 'MARKET', tag='STRANGLE_CE')
            self.order_manager.place_order('SELL', pe_instruments[0], qty, 'MARKET', tag='STRANGLE_PE')
            self.log.info(f"Strangle entry at CE:{ce_strike}/PE:{pe_strike} for {expiry_date}")
        except Exception as e:
            self.log.error(f"Strangle entry failed: {str(e)}")

    def manage_hedges(self):
        for position in self.position_manager.positions.get('net', []):
            if position['quantity'] >= 0 or position['product'] != 'MIS':
                continue

            entry_price = abs(position['average_price'])
            current_price = abs(position['last_price'])
            pnl_pct = (current_price - entry_price)/entry_price

            if pnl_pct <= -HEDGE_LOSS_THRESHOLD  and BUY_HEDGE:
                strike = position['strike']
                expiry = position['expiry']
                option_type = position['instrument_type']
                new_strike = strike - ADJACENCY_GAP if option_type == 'PE' else strike + ADJACENCY_GAP

                if self.position_manager.existing_position_check(expiry, new_strike, option_type):
                    self.log.info(f"Existing position at {new_strike}. Skipping hedge.")
                    continue

                instruments = filter_instruments(self.instrument_manager.nifty_instruments,
                                                expiry, option_type, new_strike)
                if instruments:
                    try:
                        self.order_manager.place_order('SELL', instruments[0], position['quantity'], 'MARKET', tag='HEDGE')
                        self.log.info(f"Added hedge at {new_strike} for {option_type}")
                    except Exception as e:
                        self.log.error(f"Hedge placement failed: {str(e)}")

    def manage_profit_booking(self):
        for position in self.position_manager.positions.get('net', []):
            if position['quantity'] >= 0:
                continue

            entry_price = abs(position['average_price'])
            current_price = abs(position['last_price'])
            profit_pct = (entry_price - current_price)/entry_price

            if profit_pct >= PROFIT_THRESHOLD:
                sl_price = entry_price * (1 - STOPLOSS_THRESHOLD * profit_pct)
                try:
                    self.order_manager.modify_order(position['order_id'], sl_price)
                    self.log.info(f"Updated SL for {position['tradingsymbol']} to {sl_price}")
                except Exception as e:
                    self.log.error(f"SL update failed: {str(e)}")

                new_expiry = get_expiry_date('monthly' if FAR_SELL_ADD else 'weekly')
                instruments = filter_instruments(self.instrument_manager.nifty_instruments,
                                                new_expiry, position['instrument_type'],
                                                position['strike'])
                if instruments:
                    try:
                        self.order_manager.place_order('SELL', instruments[0], position['quantity'], 'MARKET', tag='PROFIT_ADD')
                        self.log.info(f"Added profit booking order at {position['strike']}")
                    except Exception as e:
                        self.log.error(f"Profit booking order failed: {str(e)}")

                # Add weekly hedge buy
                hedge_expiry = get_expiry_date('weekly')
                buy_strike = position['strike'] + (position['average_price'] * 0.5)
                buy_instruments = filter_instruments(self.instrument_manager.nifty_instruments,
                                                    hedge_expiry, position['instrument_type'],
                                                    buy_strike)
                if buy_instruments:
                    try:
                        required_qty = abs(position['quantity']) - self.get_active_buy_qty(position['instrument_type'])
                        if required_qty > 0:
                            self.order_manager.place_order('BUY', buy_instruments[0], required_qty, 'MARKET', tag='HEDGE_BUY')
                            self.log.info(f"Added weekly hedge buy at {buy_strike}")
                    except Exception as e:
                        self.log.error(f"Hedge buy placement failed: {str(e)}")

    def manage_expiry_rollover(self):
        now = datetime.datetime.now()
        for position in self.position_manager.positions.get('net', []):
            expiry_date = datetime.datetime.strptime(position['expiry'], '%Y-%m-%d').date()
            if (expiry_date - now.date()).days > 3 or position['quantity'] == 0:
                continue

            # Close expiring position
            try:
                instrument = self.instrument_manager.get_instrument(position['instrument_token'])
                self.order_manager.place_order(
                    'BUY' if position['quantity'] < 0 else 'SELL',
                    instrument,
                    abs(position['quantity']),
                    'MARKET',
                    tag='ROLLOVER_CLOSE'
                )
                self.log.info(f"Closed expiring position {position['tradingsymbol']}")
            except Exception as e:
                self.log.error(f"Rollover close failed: {str(e)}")
                continue

            # Calculate new strike and expiry
            new_expiry = get_expiry_date('monthly' if position['tag'] in ['STRADDLE','STRANGLE'] else 'weekly')
            new_strike = position['strike'] + (position['average_price'] * 0.5)

            # Place new position
            instruments = filter_instruments(self.instrument_manager.nifty_instruments,
                                            new_expiry, position['instrument_type'],
                                            new_strike)
            if instruments:
                try:
                    qty = position['quantity'] * 2 if 'HEDGE' in position['tag'] else position['quantity']
                    self.order_manager.place_order(
                        'SELL' if qty < 0 else 'BUY',
                        instruments[0],
                        abs(qty),
                        'MARKET',
                        tag=position['tag'] + '_ROLLOVER'
                    )
                    self.log.info(f"Rolled over to new position {instruments[0]['tradingsymbol']}")
                except Exception as e:
                    self.log.error(f"Rollover placement failed: {str(e)}")

    def check_profit_targets(self):
        net_profit = self.position_manager.calculate_unrealized_pnl()
        if net_profit >= PROFIT_POINTS * NIFTY_LOT_SIZE:  # 75 Rs per point
            self.log.info(f"Profit target {PROFIT_POINTS} points reached. Closing all.")
            self.close_all_positions()
            return True
        return False

    def get_active_buy_qty(self, option_type):
        return sum(
            p['quantity'] for p in self.position_manager.positions.get('net', [])
            if p['instrument_type'] == option_type and p['quantity'] > 0
        )

    def close_all_positions(self):
        self.log.info("Initiating full position closure")
        for position in self.position_manager.positions.get('net', []):
            if position['quantity'] == 0:
                continue

            instrument = self.instrument_manager.get_instrument(position['instrument_token'])
            if not instrument:
                continue

            try:
                self.order_manager.place_order(
                    'BUY' if position['quantity'] < 0 else 'SELL',
                    instrument,
                    abs(position['quantity']),
                    'MARKET',
                    tag='SHUTDOWN_CLOSE'
                )
                self.log.info(f"Closed position {instrument['tradingsymbol']}")
            except Exception as e:
                self.log.error(f"Position closure failed: {str(e)}")
