# order_manager.py
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from kiteconnect import KiteConnect
from config import Config
from utils.helpers import Helpers
from utils.logger import logger

logging.basicConfig(level=logging.INFO)

class OrderManager:
    def __init__(self, kite: KiteConnect):
        self.kite = kite
        self.position_cache = {}
        self.order_cache = {}
        self.last_order_time = time.time()
        self.instruments_cache = Helpers.fetch_instruments(self.kite)
        
    def _get_instrument_token(self, instrument_type: str, expiry: str, strike: float) -> str:
        """Get instrument token from cached data with validation"""
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
        """Get nearest valid expiry date"""
        expiries = sorted(self.instruments_cache['expiry'].unique())
        current_date = datetime.now().date()
        
        if weekly:
            return min([e for e in expiries if e > current_date])
        monthly_expiries = [e for e in expiries if e.day > 25]
        return monthly_expiries[min(2, len(monthly_expiries)-1)]

    @Helpers.retry_api_call(max_retries=3, backoff=1)
    def place_order(self, strategy_type: str, strike: float, expiry: str, quantity: int) -> Optional[List[str]]:
        """Place orders with stop-loss tracking and conflict checks"""
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

            orders = []
            if strategy_type == 'STRADDLE':
                # Place CE order
                ce_order = self.kite.place_order(
                    tradingsymbol=ce_symbol, 
                    transaction_type=self.kite.TRANSACTION_TYPE_SELL,
                    quantity=quantity,
                    **order_params
                )
                # Place PE order
                pe_order = self.kite.place_order(
                    tradingsymbol=pe_symbol,
                    transaction_type=self.kite.TRANSACTION_TYPE_SELL,
                    quantity=quantity,
                    **order_params
                )
                # Track stop-loss orders
                self.order_cache[ce_order] = {
                    'type': 'CE',
                    'stop_loss_id': self._place_stop_loss(ce_symbol, quantity)
                }
                self.order_cache[pe_order] = {
                    'type': 'PE', 
                    'stop_loss_id': self._place_stop_loss(pe_symbol, quantity)
                }
                orders = [ce_order, pe_order]
            
            elif strategy_type == 'STRANGLE':
                # Calculate strangle strikes with validation
                ce_strike = strike + 1000
                pe_strike = strike - 1000
                while (ce_strike - strike) < 1000:
                    ce_strike += Config.ADJACENCY_GAP
                while (strike - pe_strike) < 1000:
                    pe_strike -= Config.ADJACENCY_GAP
                
                ce_symbol = self._get_instrument_token("CE", expiry, ce_strike)
                pe_symbol = self._get_instrument_token("PE", expiry, pe_strike)
                
                # Place orders
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
                # Track stop-loss orders
                self.order_cache[ce_order] = {
                    'type': 'CE',
                    'stop_loss_id': self._place_stop_loss(ce_symbol, quantity)
                }
                self.order_cache[pe_order] = {
                    'type': 'PE',
                    'stop_loss_id': self._place_stop_loss(pe_symbol, quantity)
                }
                orders = [ce_order, pe_order]

            logger.info(f"Orders placed successfully: {orders}")
            return orders

        except Exception as e:
            logger.error(f"Order placement failed: {str(e)}")
            return self._place_limit_order_fallback(strategy_type, strike, expiry, quantity)

    def _check_existing_positions(self, strategy_type: str, strike: float, expiry: str) -> bool:
        """Enhanced conflict checking with strike proximity validation"""
        positions = self.kite.positions()['net']
        orders = self.kite.orders()

        # Check positions
        for pos in positions:
            pos_expiry = datetime.strptime(pos['expiry'], '%Y-%m-%d').date()
            if (pos['tradingsymbol'].startswith('NIFTY') and
                pos_expiry == expiry and
                abs(pos['strike'] - strike) <= Config.ADJACENCY_GAP):
                return True

        # Check pending orders
        for order in orders:
            if order['status'] in ['OPEN', 'TRIGGER PENDING']:
                order_expiry = datetime.strptime(order['expiry'], '%Y-%m-%d').date()
                if (order['tradingsymbol'].startswith('NIFTY') and
                    order_expiry == expiry and
                    abs(order['strike'] - strike) <= Config.ADJACENCY_GAP):
                    return True

        return False

    def _place_stop_loss(self, symbol: str, quantity: int) -> Optional[str]:
        """Place stop-loss order with price calculation"""
        try:
            ltp = self.kite.ltp(f"NFO:{symbol}")[f"NFO:{symbol}"]['last_price']
            sl_price = round(ltp * 1.10, 1)  # 10% above LTP for sell orders
            
            return self.kite.place_order(
                tradingsymbol=symbol,
                transaction_type=self.kite.TRANSACTION_TYPE_BUY,
                quantity=quantity,
                exchange='NFO',
                order_type=self.kite.ORDER_TYPE_SL,
                product=self.kite.PRODUCT_MIS,
                trigger_price=sl_price,
                validity=self.kite.VALIDITY_DAY
            )
        except Exception as e:
            logger.error(f"Stop-loss placement failed for {symbol}: {str(e)}")
            return None

    def adjust_orders_on_profit(self, position: Dict) -> None:
        """Profit-triggered adjustments with stop-loss updates"""
        try:
            entry_value = position['entry_price'] * position['quantity'] * Config.LOT_SIZE
            current_value = position['last_price'] * position['quantity'] * Config.LOT_SIZE
            profit_pct = ((current_value - entry_value) / entry_value) * 100
            
            if profit_pct >= 25:
                # Update stop loss
                self.kite.modify_order(
                    order_id=position['stop_loss_id'],
                    trigger_price=position['entry_price'] * 0.9
                )
                
                # Add new position
                new_expiry = self._get_nearest_expiry(Config.FAR_SELL_ADD)
                new_quantity = position['quantity'] * Config.LOT_SIZE
                new_order_ids = self.place_order(
                    strategy_type=position['strategy_type'],
                    strike=position['strike'],
                    expiry=new_expiry,
                    quantity=new_quantity
                )
                
                if new_order_ids:
                    logger.info(f"Profit adjustment successful for {position['id']}")
                else:
                    logger.warning(f"Profit adjustment failed for {position['id']}")

        except Exception as e:
            logger.error(f"Profit adjustment failed: {str(e)}")
            self._handle_order_error(position)

    @Helpers.retry_api_call(max_retries=2, backoff=1)
    def create_hedge_orders(self, spot_price: float, is_loss_hedge: bool = False) -> None:
        """Create hedge orders with premium validation"""
        if not Config.BUY_HEDGE and is_loss_hedge:
            return

        expiry = self._get_nearest_expiry(weekly=True)
        distance = Config.ADJACENCY_GAP * (2 if is_loss_hedge else 1)
        quantity = Config.LOT_SIZE if Config.HEDGE_ONE_LOT else self._calculate_hedge_quantity()

        for direction in ['CE', 'PE']:
            strike = Helpers.get_nearest_strike(
                spot_price + (distance if direction == 'CE' else -distance)
            )
            try:
                symbol = self._get_instrument_token(direction, expiry, strike)
                if self._get_premium(symbol) > Config.HEDGE_PREMIUM_THRESHOLD:
                    continue
                
                order_id = self.kite.place_order(
                    tradingsymbol=symbol,
                    exchange='NFO',
                    product=self.kite.PRODUCT_MIS,
                    order_type=self.kite.ORDER_TYPE_SL,
                    transaction_type=self.kite.TRANSACTION_TYPE_BUY,
                    quantity=quantity,
                    validity=self.kite.VALIDITY_DAY,
                    trigger_price=strike * 1.05
                )
                self.order_cache[order_id] = {'type': 'HEDGE', 'strike': strike}
                
            except Exception as e:
                logger.error(f"Hedge order failed ({direction} {strike}): {str(e)}")

    def _place_limit_order_fallback(self, strategy_type: str, strike: float, 
                                  expiry: str, quantity: int) -> Optional[List[str]]:
        """Limit order fallback with price calculation"""
        try:
            orders = []
            for opt_type in ['CE', 'PE']:
                symbol = self._get_instrument_token(opt_type, expiry, strike)
                ltp = self.kite.ltp(f"NFO:{symbol}")[f"NFO:{symbol}"]['last_price']
                limit_price = round(ltp * 0.99, 1) if strategy_type == 'SELL' else round(ltp * 1.01, 1)
                
                order_id = self.kite.place_order(
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
                orders.append(order_id)
                logger.info(f"Limit order placed: {order_id}")
            
            return orders
            
        except Exception as e:
            logger.critical(f"Limit order fallback failed: {str(e)}")
            return None

    def _calculate_hedge_quantity(self) -> int:
        """Calculate hedge quantity based on open positions"""
        positions = self.kite.positions()['net']
        nifty_positions = [p for p in positions if p['tradingsymbol'].startswith('NIFTY')]
        return sum(abs(p['quantity']) for p in nifty_positions) // len(nifty_positions) if nifty_positions else Config.LOT_SIZE

    def sync_positions(self) -> None:
        """Synchronize positions with broker data"""
        try:
            self.position_cache = {
                pos['tradingsymbol']: pos for pos in self.kite.positions()['net']
            }
            self.order_cache = {
                order['order_id']: order for order in self.kite.orders()
            }
            logger.debug("Position synchronization completed")
        except Exception as e:
            logger.error(f"Position sync failed: {str(e)}")
            raise

    def _handle_order_error(self, position: Dict) -> None:
        """Order error recovery with retry logic"""
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

    def _get_premium(self, tradingsymbol: str) -> float:
        """Get current premium with error handling"""
        try:
            return self.kite.ltp(f"NFO:{tradingsymbol}")[f"NFO:{tradingsymbol}"]['last_price']
        except Exception as e:
            logger.error(f"Premium check failed for {tradingsymbol}: {str(e)}")
            return float('inf')
