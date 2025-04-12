import logging
import time
from typing import Dict, Optional, Tuple
from kiteconnect import KiteConnect, KiteTicker
from config import (
    BIAS,
    ADJACENCY_GAP,
    PROFIT_POINTS,
    SHUTDOWN_LOSS,
    HEDGE_ONE_LOT,
    BUY_HEDGE,
    FAR_SELL_ADD,
    LOT_SIZE,
    POSITION_STOPLOSS,
    HEDGE_PREMIUM_THRESHOLD
)
from utils.logger import configure_logger
from utils.helpers import Helpers

configure_logger()
logger = logging.getLogger(__name__)

class OrderManager:
    def __init__(self, kite: KiteConnect):
        self.kite = kite
        self.position_cache = {}
        self.order_cache = {}
        self.last_order_time = time.time()
        self.instruments_cache = Helpers.fetch_instruments(self.kite)
        
    def _get_instrument_token(self, instrument_type: str, expiry: str, strike: float) -> str:
        """Get instrument token from cached data"""
        expiry_date = expiry.strftime('%Y-%m-%d') if isinstance(expiry, datetime.date) else expiry
        filtered = self.instruments_cache[
            (self.instruments_cache['name'] == 'NIFTY') &
            (self.instruments_cache['expiry'] == expiry_date) &
            (self.instruments_cache['strike'] == strike) &
            (self.instruments_cache['instrument_type'] == instrument_type)
        ]
        if not filtered.empty:
            return filtered.iloc[0]['tradingsymbol']
        raise ValueError(f"Instrument not found: {expiry}-{strike}-{instrument_type}")

    def _get_nearest_expiry(self, weekly: bool = True) -> datetime.date:
        """Get nearest weekly or monthly expiry date"""
        expiries = sorted(self.instruments_cache['expiry'].unique())
        if weekly:
            return min([e for e in expiries if e > datetime.now().date()])
        return [e for e in expiries if e.day > 25][min(3, len(expiries)-1)]

    def place_order(self, strategy_type: str, strike: float, expiry: str, quantity: int) -> Optional[int]:
        """Place order with conflict checks and retry logic"""
        if self._check_existing_positions(strategy_type, strike, expiry):
            logger.warning(f"Duplicate position prevented for {strategy_type} {strike} {expiry}")
            return None

        try:
            ce_symbol = self._get_instrument_token("CE", expiry, strike)
            pe_symbol = self._get_instrument_token("PE", expiry, strike)
            
            order_params = {
                'variety': self.kite.VARIETY_REGULAR,
                'exchange': 'NFO',
                'product': self.kite.PRODUCT_MIS,
                'order_type': self.kite.ORDER_TYPE_MARKET,
                'validity': self.kite.VALIDITY_DAY
            }

            if strategy_type == 'STRADDLE':
                ce_order = self.kite.place_order(
                    tradingsymbol=ce_symbol, 
                    transaction_type=self.kite.TRANSACTION_TYPE_SELL,
                    quantity=quantity,
                    **order_params
                )
                pe_order = self.kite.place_order(
                    tradingsymbol=pe_symbol,
                    transaction_type=self.kite.TRANSACTION_TYPE_SELL,
                    quantity=quantity,
                    **order_params
                )
                return [ce_order, pe_order]
            
            elif strategy_type == 'STRANGLE':
                ce_strike = strike + 1000
                while (ce_strike - strike) < 1000:
                    ce_strike += 100
                pe_strike = strike - 1000
                while (strike - pe_strike) < 1000:
                    pe_strike -= 100
                
                ce_symbol = self._get_instrument_token("CE", expiry, ce_strike)
                pe_symbol = self._get_instrument_token("PE", expiry, pe_strike)
                
                ce_order = self.kite.place_order(
                    tradingsymbol=ce_symbol,
                    transaction_type=self.kite.TRANSACTION_TYPE_SELL,
                    quantity=quantity,
                    **order_params
                )
                pe_order = self.kite.place_order(
                    tradingsymbol=pe_symbol,
                    transaction_type=self.kite.TRANSACTION_TYPE_SELL,
                    quantity=quantity,
                    **order_params
                )
                return [ce_order, pe_order]

        except Exception as e:
            logger.error(f"Order placement failed: {str(e)}")
            return self._place_limit_order_fallback(strategy_type, strike, expiry, quantity)

    def _check_existing_positions(self, strategy_type: str, strike: float, expiry: str) -> bool:
        """Check for existing positions/orders with same parameters"""
        positions = self.kite.positions()['net']
        orders = self.kite.orders()

        for pos in positions:
            if (pos['tradingsymbol'].startswith('NIFTY') and
                pos['expiry'] == expiry and
                abs(pos['strike'] - strike) <= ADJACENCY_GAP):
                return True

        for order in orders:
            if (order['status'] in ['OPEN', 'TRIGGER PENDING'] and
                order['tradingsymbol'].startswith('NIFTY') and
                order['expiry'] == expiry):
                return True

        return False

    def adjust_orders_on_profit(self, position: Dict) -> None:
        """Manage profit-triggered adjustments with proper calculation"""
        try:
            entry_value = position['entry_price'] * position['quantity'] * LOT_SIZE
            current_value = position['last_price'] * position['quantity'] * LOT_SIZE
            profit_pct = ((current_value - entry_value) / entry_value) * 100
            
            if profit_pct >= 25:
                self.kite.modify_order(
                    order_id=position['stop_loss_id'],
                    trigger_price=position['entry_price'] * 0.9
                )
                
                new_expiry = self._get_nearest_expiry(FAR_SELL_ADD)
                new_quantity = position['quantity'] * LOT_SIZE
                self.place_order(
                    strategy_type=position['strategy_type'],
                    strike=position['strike'],
                    expiry=new_expiry,
                    quantity=new_quantity
                )
                logger.info(f"Profit-triggered adjustment completed for {position['id']}")

        except Exception as e:
            logger.error(f"Profit adjustment failed: {str(e)}")
            self._handle_order_error(position)

    def create_hedge_orders(self, spot_price: float, is_loss_hedge: bool = False) -> None:
        """Create hedge orders with premium threshold check"""
        if not BUY_HEDGE and is_loss_hedge:
            return

        expiry = self._get_nearest_expiry(weekly=True)
        distance = ADJACENCY_GAP * (2 if is_loss_hedge else 1)
        quantity = LOT_SIZE if HEDGE_ONE_LOT else self._calculate_hedge_quantity()

        for direction in ['CE', 'PE']:
            strike = spot_price + (distance if direction == 'CE' else -distance)
            strike = strike - (strike % 50)
            try:
                symbol = self._get_instrument_token(direction, expiry, strike)
                if self._get_premium(symbol) > HEDGE_PREMIUM_THRESHOLD:
                    continue
                
                self.kite.place_order(
                    tradingsymbol=symbol,
                    exchange='NFO',
                    product=self.kite.PRODUCT_MIS,
                    order_type=self.kite.ORDER_TYPE_SL,
                    transaction_type=self.kite.TRANSACTION_TYPE_BUY,
                    quantity=quantity,
                    validity=self.kite.VALIDITY_DAY,
                    trigger_price=strike * 1.05
                )
            except Exception as e:
                logger.error(f"Hedge order failed ({direction} {strike}): {str(e)}")

    def _place_limit_order_fallback(self, strategy_type: str, strike: float, 
                                 expiry: str, quantity: int) -> Optional[int]:
        """Fallback to limit order with price calculation"""
        try:
            instrument_type = 'CE' if strategy_type == 'STRADDLE' else 'PE'
            symbol = self._get_instrument_token(instrument_type, expiry, strike)
            ltp = self.kite.ltp(f"NFO:{symbol}")[f"NFO:{symbol}"]['last_price']
            limit_price = ltp * 0.99 if 'SELL' in strategy_type else ltp * 1.01
            
            return self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange='NFO',
                product=self.kite.PRODUCT_MIS,
                order_type=self.kite.ORDER_TYPE_LIMIT,
                price=limit_price,
                validity=self.kite.VALIDITY_DAY,
                tradingsymbol=symbol,
                transaction_type=self.kite.TRANSACTION_TYPE_SELL,
                quantity=quantity
            )
        except Exception as e:
            logger.critical(f"Limit order fallback failed: {str(e)}")
            return None

    def _calculate_hedge_quantity(self) -> int:
        """Calculate hedge quantity based on current positions"""
        positions = self.kite.positions()['net']
        nifty_positions = [p for p in positions if p['tradingsymbol'].startswith('NIFTY')]
        return sum(abs(p['quantity']) for p in nifty_positions) // len(nifty_positions) if nifty_positions else LOT_SIZE

    def adjust_strikes_recursively(self, base_strike: float, step: int = 1) -> float:
        """Recursively adjust strikes to find non-conflicting level"""
        new_strike = base_strike + (ADJACENCY_GAP * step)
        if not self._check_existing_positions('ANY', new_strike, self._get_nearest_expiry()):
            return new_strike
        return self.adjust_strikes_recursively(base_strike, step + 1)

    def sync_positions(self) -> None:
        """Synchronize local position cache with broker"""
        self.position_cache = {
            pos['tradingsymbol']: pos for pos in self.kite.positions()['net']
        }
        self.order_cache = {
            order['order_id']: order for order in self.kite.orders()
        }
        logger.debug("Position synchronization completed")

    def _handle_order_error(self, position: Dict) -> None:
        """Handle order errors with retry logic"""
        retry_count = 0
        while retry_count < 3:
            try:
                self.kite.cancel_order(order_id=position['order_id'])
                time.sleep(1)
                self.place_order(**position)
                break
            except Exception as e:
                logger.error(f"Order recovery failed (attempt {retry_count+1}): {str(e)}")
                retry_count += 1
                time.sleep(5)

    def _close_position(self, position: Dict) -> None:
        """Close position with market order fallback to limit"""
        try:
            transaction = self.kite.BUY if position['quantity'] < 0 else self.kite.SELL
            return self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange='NFO',
                tradingsymbol=position['tradingsymbol'],
                transaction_type=transaction,
                quantity=abs(position['quantity']),
                product=self.kite.PRODUCT_MIS,
                order_type=self.kite.ORDER_TYPE_MARKET
            )
        except Exception as e:
            logger.error("Market order failed, falling back to limit")
            ltp = self.kite.ltp(f"NFO:{position['tradingsymbol']}")[f"NFO:{position['tradingsymbol']}"]['last_price']
            return self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange='NFO',
                tradingsymbol=position['tradingsymbol'],
                transaction_type=transaction,
                quantity=abs(position['quantity']),
                product=self.kite.PRODUCT_MIS,
                order_type=self.kite.ORDER_TYPE_LIMIT,
                price=ltp * 0.95 if transaction == self.kite.BUY else ltp * 1.05
            )

    def _get_premium(self, tradingsymbol: str) -> float:
        """Get current premium for an instrument"""
        try:
            return self.kite.ltp(f"NFO:{tradingsymbol}")[f"NFO:{tradingsymbol}"]['last_price']
        except Exception as e:
            logger.error(f"Premium check failed for {tradingsymbol}: {str(e)}")
            return float('inf')
