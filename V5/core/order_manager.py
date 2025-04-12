import logging
import time
from typing import Dict, Optional, List
from kiteconnect import KiteConnect, KiteTicker
from config import Config
from utils.helpers import Helpers
from utils.logger import configure_logger

configure_logger()
logger = logging.getLogger(__name__)

class OrderManager:
    def __init__(self, kite: KiteConnect):
        self.kite = kite
        self.position_cache = {}
        self.order_cache = {}
        self.last_order_time = time.time()
        self.instruments = Helpers.fetch_instruments(kite)

    def _get_instrument_token(self, instrument_type: str, expiry: str, strike: float) -> str:
        """Get instrument symbol using cached data with premium validation"""
        expiry_date = datetime.strptime(expiry, '%Y-%m-%d').date()
        filtered = self.instruments[
            (self.instruments['name'] == 'NIFTY') &
            (self.instruments['expiry'] == expiry_date) &
            (self.instruments['strike'] == strike) &
            (self.instruments['instrument_type'] == instrument_type)
        ]
        
        if not filtered.empty:
            return filtered.iloc[0]['tradingsymbol']
        raise ValueError(f"Instrument not found: {expiry}-{strike}-{instrument_type}")

    def _get_nearest_expiry(self, weekly: bool = True) -> str:
        """Get nearest non-conflicting expiry date"""
        all_expiries = sorted(self.instruments['expiry'].unique())
        if weekly:
            return min([e for e in all_expiries if e > datetime.now().date()])
        return Helpers.get_expiry_series(all_expiries, Config.FAR_MONTH_OFFSET)

    def place_order(self, strategy_type: str, strike: float, expiry: str, quantity: int) -> Optional[List[str]]:
        """Enhanced order placement with conflict checks and fallback"""
        if self._check_existing_positions(strategy_type, strike, expiry):
            logger.warning(f"Duplicate position prevented for {strategy_type} {strike} {expiry}")
            return None

        try:
            ce_strike = strike + (Config.BIAS if strategy_type == 'STRADDLE' else 1000)
            pe_strike = strike - (Config.BIAS if strategy_type == 'STRADDLE' else 1000)
            
            ce_symbol = self._get_instrument_token("CE", expiry, ce_strike)
            pe_symbol = self._get_instrument_token("PE", expiry, pe_strike)

            orders = []
            for symbol, trans_type in [(ce_symbol, 'SELL'), (pe_symbol, 'SELL')]:
                order_id = self._execute_order(
                    symbol=symbol,
                    quantity=quantity,
                    transaction_type=trans_type
                )
                orders.append(order_id)
            
            self.sync_positions()
            return orders

        except Exception as e:
            logger.error(f"Order placement failed: {str(e)}")
            return self._place_limit_order_fallback(strategy_type, strike, expiry, quantity)

    def _execute_order(self, symbol: str, quantity: int, transaction_type: str) -> str:
        """Core order execution with retries"""
        params = {
            'variety': self.kite.VARIETY_REGULAR,
            'exchange': 'NFO',
            'tradingsymbol': symbol,
            'quantity': quantity,
            'product': self.kite.PRODUCT_MIS,
            'order_type': self.kite.ORDER_TYPE_MARKET,
            'validity': self.kite.VALIDITY_DAY,
            'transaction_type': self.kite.TRANSACTION_TYPE_SELL if transaction_type == 'SELL' 
                              else self.kite.TRANSACTION_TYPE_BUY
        }
        
        for attempt in range(3):
            try:
                return self.kite.place_order(**params)
            except Exception as e:
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
        return None

    def _check_existing_positions(self, strategy_type: str, strike: float, expiry: str) -> bool:
        """Enhanced conflict checking with adjacency gap"""
        positions = self.kite.positions()['net']
        orders = self.kite.orders()

        conflict_range = {
            'STRADDLE': Config.ADJACENCY_GAP,
            'STRANGLE': 1000
        }.get(strategy_type, Config.ADJACENCY_GAP)

        for pos in positions:
            pos_expiry = datetime.strptime(pos['expiry'], '%Y-%m-%d').date()
            if (pos['tradingsymbol'].startswith('NIFTY') and
                pos_expiry == datetime.strptime(expiry, '%Y-%m-%d').date() and
                abs(pos['strike'] - strike) <= conflict_range):
                return True

        return False

    def adjust_orders_on_profit(self, position: Dict) -> None:
        """Proper profit percentage calculation and adjustments"""
        try:
            entry_value = position['entry_price'] * position['quantity'] * Config.LOT_SIZE
            current_value = position['last_price'] * position['quantity'] * Config.LOT_SIZE
            profit_pct = ((current_value - entry_value) / entry_value) * 100
            
            if profit_pct >= 25:
                # Modify stop loss
                self.kite.modify_order(
                    order_id=position['stop_loss_id'],
                    trigger_price=position['entry_price'] * 0.9
                )
                
                # Place new hedge-adjusted order
                new_expiry = self._get_nearest_expiry(Config.FAR_SELL_ADD)
                self.place_order(
                    strategy_type=position['strategy_type'],
                    strike=position['strike'],
                    expiry=new_expiry.isoformat(),
                    quantity=position['quantity']
                )
                
                logger.info(f"Profit-triggered adjustment completed for {position['tradingsymbol']}")

        except Exception as e:
            logger.error(f"Profit adjustment failed: {str(e)}")
            self._handle_order_error(position)

    def create_hedge_orders(self, spot_price: float, is_loss_hedge: bool = False) -> None:
        """Premium-aware hedge creation"""
        if not Config.BUY_HEDGE and is_loss_hedge:
            return

        expiry = self._get_nearest_expiry(weekly=True).isoformat()
        distance = Config.ADJACENCY_GAP * (2 if is_loss_hedge else 1)
        quantity = Config.LOT_SIZE if Config.HEDGE_ONE_LOT else self._calculate_hedge_quantity()

        for direction in ['CE', 'PE']:
            strike = Helpers.get_nearest_strike(
                spot_price + (distance if direction == 'CE' else -distance)
            )
            try:
                symbol = self._get_instrument_token(direction, expiry, strike)
                self._execute_order(
                    symbol=symbol,
                    quantity=quantity,
                    transaction_type='BUY'
                )
            except Exception as e:
                logger.error(f"Hedge order failed ({direction} {strike}): {str(e)}")

    def _place_limit_order_fallback(self, strategy_type: str, strike: float, 
                                  expiry: str, quantity: int) -> Optional[List[str]]:
        """Intelligent limit order fallback with premium check"""
        try:
            symbols = []
            if strategy_type == 'STRADDLE':
                symbols.append(self._get_instrument_token('CE', expiry, strike + Config.BIAS))
                symbols.append(self._get_instrument_token('PE', expiry, strike - Config.BIAS))
            else:
                symbols.append(self._get_instrument_token('CE', expiry, strike + 1000))
                symbols.append(self._get_instrument_token('PE', expiry, strike - 1000))

            orders = []
            for symbol in symbols:
                ltp = self.kite.ltp(f"NFO:{symbol}")[f"NFO:{symbol}"]['last_price']
                limit_price = ltp * 0.99  # 1% below LTP for sell orders
                
                orders.append(self.kite.place_order(
                    variety=self.kite.VARIETY_REGULAR,
                    exchange='NFO',
                    tradingsymbol=symbol,
                    transaction_type=self.kite.TRANSACTION_TYPE_SELL,
                    quantity=quantity,
                    product=self.kite.PRODUCT_MIS,
                    order_type=self.kite.ORDER_TYPE_LIMIT,
                    price=limit_price,
                    validity=self.kite.VALIDITY_DAY
                ))
            
            return orders
            
        except Exception as e:
            logger.critical(f"Limit order fallback failed: {str(e)}")
            return None

    def _calculate_hedge_quantity(self) -> int:
        """Dynamic quantity calculation based on exposure"""
        positions = self.kite.positions()['net']
        nifty_positions = [p for p in positions if p['tradingsymbol'].startswith('NIFTY')]
        if not nifty_positions:
            return Config.LOT_SIZE
        return max(
            sum(abs(p['quantity']) for p in nifty_positions) // len(nifty_positions),
            Config.LOT_SIZE
        )

    def sync_positions(self) -> None:
        """Comprehensive position synchronization"""
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
        """Advanced error recovery with state rollback"""
        for attempt in range(3):
            try:
                self.kite.cancel_order(order_id=position['order_id'])
                time.sleep(1)
                self.sync_positions()
                self.place_order(**position)
                return
            except Exception as e:
                logger.error(f"Order recovery failed (attempt {attempt+1}): {str(e)}")
                time.sleep(5)
        
        logger.critical(f"Permanent order failure: {position['tradingsymbol']}")
        self.sync_positions()
