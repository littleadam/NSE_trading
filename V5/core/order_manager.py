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
        self.rate_limit_delay = 1  # Seconds between orders
        self.position_tracker = PositionTracker(kite)
        
    def _get_instrument_token(self, instrument_type: str, expiry: datetime.date, strike: float) -> str:
        """Get instrument token from cached data with validation"""
        expiry_str = expiry.strftime('%Y-%m-%d') if isinstance(expiry, datetime.date) else expiry
        filtered = self.instruments_cache[
            (self.instruments_cache['name'] == 'NIFTY') &
            (self.instruments_cache['expiry'] == expiry_str) &
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
            return min([datetime.strptime(e, '%Y-%m-%d').date() for e in expiries 
                       if datetime.strptime(e, '%Y-%m-%d').date() > current_date])
        monthly_expiries = [datetime.strptime(e, '%Y-%m-%d').date() for e in expiries 
                           if datetime.strptime(e, '%Y-%m-%d').day > 25]
        return monthly_expiries[min(2, len(monthly_expiries)-1)]

    @Helpers.retry_api_call(max_retries=3, backoff=1)
    def place_order(self, strategy_type: str, strike: float, expiry: datetime.date, 
                   quantity: int) -> Optional[List[str]]:
        """Place orders with rate limiting and conflict checks"""
        # Rate limiting
        elapsed = time.time() - self.last_order_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
            
        # Close any opposing positions first
        self.close_opposite_positions(strategy_type, expiry, strike)

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
                ce_strike = strike + Config.STRANGLE_GAP
                pe_strike = strike - Config.STRANGLE_GAP
                while (ce_strike - strike) < Config.STRANGLE_GAP:
                    ce_strike += Config.ADJACENCY_GAP
                while (strike - pe_strike) < Config.STRANGLE_GAP:
                    pe_strike -= Config.ADJACENCY_GAP
                
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
            self.last_order_time = time.time()
            return orders

        except Exception as e:
            logger.error(f"Order placement failed: {str(e)}")
            return self._place_limit_order_fallback(strategy_type, strike, expiry, quantity)

    def close_opposite_positions(self, strategy_type: str, expiry: datetime.date, strike: float) -> List[str]:
        """Close any existing BUY positions before placing new SELL orders"""
        close_orders = []
        self.position_tracker.update_positions()
        positions = self.position_tracker.get_positions()
        
        for pos in positions:
            if (pos['expiry'] == expiry and 
                abs(pos['strike'] - strike) <= Config.ADJACENCY_GAP and
                pos['transaction_type'] == self.kite.TRANSACTION_TYPE_BUY):
                try:
                    order_id = self.kite.place_order(
                        variety=self.kite.VARIETY_REGULAR,
                        exchange='NFO',
                        tradingsymbol=pos['symbol'],
                        transaction_type=self.kite.TRANSACTION_TYPE_SELL,
                        quantity=abs(pos['quantity']),
                        product=self.kite.PRODUCT_MIS,
                        order_type=self.kite.ORDER_TYPE_MARKET
                    )
                    close_orders.append(order_id)
                    logger.info(f"Closing opposite position: {pos['symbol']}")
                except Exception as e:
                    logger.error(f"Failed to close position: {str(e)}")
        
        if close_orders:
            time.sleep(1)  # Allow position updates
            self.sync_positions()
            
        return close_orders

    def _check_existing_positions(self, strategy_type: str, strike: float, expiry: datetime.date) -> bool:
        """Enhanced conflict checking with direction validation"""
        self.position_tracker.update_positions()
        positions = self.position_tracker.get_positions()
        orders = self.kite.orders()

        # Check positions
        for pos in positions:
            pos_expiry = pos['expiry']
            if (pos['symbol'].startswith('NIFTY') and
                pos_expiry == expiry and
                abs(pos['strike'] - strike) <= Config.ADJACENCY_GAP and
                pos['transaction_type'] == self.kite.TRANSACTION_TYPE_SELL):
                return True

        # Check pending orders
        for order in orders:
            if order['status'] in ['OPEN', 'TRIGGER PENDING']:
                order_expiry = datetime.strptime(order['expiry'], '%Y-%m-%d').date()
                if (order['tradingsymbol'].startswith('NIFTY') and
                    order_expiry == expiry and
                    abs(order['strike'] - strike) <= Config.ADJACENCY_GAP and
                    order['transaction_type'] == self.kite.TRANSACTION_TYPE_SELL):
                    return True

        return False

    def _place_stop_loss(self, symbol: str, quantity: int) -> Optional[str]:
        """Place stop-loss order with price calculation"""
        try:
            ltp = self.kite.ltp(f"NFO:{symbol}")[f"NFO:{symbol}"]['last_price']
            sl_price = round(ltp * 1.10, 1)
            
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
            profit_points = (current_value - entry_value) / Config.LOT_SIZE
            
            if profit_points >= Config.PROFIT_POINTS:
                self.kite.modify_order(
                    order_id=position['stop_loss_id'],
                    trigger_price=position['entry_price'] * 0.9
                )
                
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
    def _place_limit_order_fallback(self, strategy_type: str, strike: float, 
                                  expiry: datetime.date, quantity: int) -> Optional[List[str]]:
        """Limit order fallback with price calculation"""
        try:
            orders = []
            for opt_type in ['CE', 'PE']:
                symbol = self._get_instrument_token(opt_type, expiry, strike)
                ltp = self.kite.ltp(f"NFO:{symbol}")[f"NFO:{symbol}"]['last_price']
                limit_price = round(ltp * 0.99, 1)
                
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
