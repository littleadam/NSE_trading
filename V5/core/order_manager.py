import logging
import time
from typing import Dict, Optional, Tuple
from kiteconnect import KiteConnect, KiteTicker
from config import (
    BIAS,
    ADJACENCY_GAP,
    PROFIT_POINTS,
    HEDGE_ONE_LOT,
    BUY_HEDGE,
    FAR_SELL_ADD,
    LOT_SIZE
)
from utils.logger import configure_logger

configure_logger()
logger = logging.getLogger(__name__)

class OrderManager:
    def __init__(self, kite: KiteConnect):
        self.kite = kite
        self.position_cache = {}
        self.order_cache = {}
        self.last_order_time = time.time()
        
    def _get_instrument_token(self, instrument_type: str, expiry: str, strike: float) -> int:
        """Get instrument token for given parameters"""
        instruments = self.kite.instruments("NFO")
        for inst in instruments:
            if (inst['name'] == 'NIFTY' and 
                inst['expiry'] == expiry and
                inst['strike'] == strike and
                inst['instrument_type'] == instrument_type):
                return inst['tradingsymbol']
        raise ValueError(f"Instrument not found: {expiry}-{strike}-{instrument_type}")

    def _get_nearest_expiry(self, weekly: bool = True) -> str:
        """Get nearest weekly or monthly expiry date"""
        expiries = sorted(self.kite.instruments("NFO")['expiry'].unique())
        weekly_expiries = [e for e in expiries if '-' not in e]  # Assuming weekly expiries have specific format
        return weekly_expiries[0] if weekly else expiries[3]

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

            # Place straddle/strangle orders
            if strategy_type == 'STRADDLE':
                ce_order = self.kite.place_order(tradingsymbol=ce_symbol, 
                                                transaction_type=self.kite.TRANSACTION_TYPE_SELL,
                                                quantity=quantity,
                                                **order_params)
                pe_order = self.kite.place_order(tradingsymbol=pe_symbol,
                                                transaction_type=self.kite.TRANSACTION_TYPE_SELL,
                                                quantity=quantity,
                                                **order_params)
                return [ce_order, pe_order]
            
            elif strategy_type == 'STRANGLE':
                # Strangle has different strikes for CE/PE
                ce_strike = strike + 1000
                pe_strike = strike - 1000
                ce_symbol = self._get_instrument_token("CE", expiry, ce_strike)
                pe_symbol = self._get_instrument_token("PE", expiry, pe_strike)
                
                ce_order = self.kite.place_order(tradingsymbol=ce_symbol,
                                                transaction_type=self.kite.TRANSACTION_TYPE_SELL,
                                                quantity=quantity,
                                                **order_params)
                pe_order = self.kite.place_order(tradingsymbol=pe_symbol,
                                                transaction_type=self.kite.TRANSACTION_TYPE_SELL,
                                                quantity=quantity,
                                                **order_params)
                return [ce_order, pe_order]

        except Exception as e:
            logger.error(f"Order placement failed: {str(e)}")
            return self._place_limit_order_fallback(strategy_type, strike, expiry, quantity)

    def _check_existing_positions(self, strategy_type: str, strike: float, expiry: str) -> bool:
        """Check for existing positions/orders with same parameters"""
        positions = self.kite.positions()['net']
        orders = self.kite.orders()

        # Check open positions
        for pos in positions:
            if (pos['tradingsymbol'].startswith('NIFTY') and
                pos['expiry'] == expiry and
                abs(pos['strike'] - strike) <= ADJACENCY_GAP):
                return True

        # Check pending orders
        for order in orders:
            if (order['status'] in ['OPEN', 'TRIGGER PENDING'] and
                order['tradingsymbol'].startswith('NIFTY') and
                order['expiry'] == expiry):
                return True

        return False

    def adjust_orders_on_profit(self, position: Dict) -> None:
        """Manage profit-triggered adjustments"""
        if position['profit_pct'] >= 25:
            try:
                # Modify stop loss to 90%
                self.kite.modify_order(
                    order_id=position['stop_loss_id'],
                    trigger_price=position['entry_price'] * 0.9
                )
                
                # Place new sell order
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
        """Create hedge orders based on current market conditions"""
        if not BUY_HEDGE and is_loss_hedge:
            return

        expiry = self._get_nearest_expiry(weekly=True)
        distance = ADJACENCY_GAP * (2 if is_loss_hedge else 1)
        quantity = LOT_SIZE if HEDGE_ONE_LOT else self._calculate_hedge_quantity()

        for direction in ['CE', 'PE']:
            strike = spot_price + (distance if direction == 'CE' else -distance)
            strike = strike - (strike % 50)  # Round to nearest 50
            try:
                symbol = self._get_instrument_token(direction, expiry, strike)
                self.kite.place_order(
                    tradingsymbol=symbol,
                    exchange='NFO',
                    product=self.kite.PRODUCT_MIS,
                    order_type=self.kite.ORDER_TYPE_SL,
                    transaction_type=self.kite.TRANSACTION_TYPE_BUY,
                    quantity=quantity,
                    validity=self.kite.VALIDITY_DAY,
                    trigger_price=strike * 1.05  # 5% buffer
                )
            except Exception as e:
                logger.error(f"Hedge order failed ({direction} {strike}): {str(e)}")

    def _place_limit_order_fallback(self, strategy_type: str, strike: float, 
                                 expiry: str, quantity: int) -> Optional[int]:
        """Fallback to limit order with price calculation"""
        try:
            ltp = self.kite.ltp([f"NFO:NIFTY{expiry}{strike}{'CE' if strategy_type == 'STRADDLE' else 'PE'}"])
            limit_price = ltp['last_price'] * (0.99 if 'SELL' in strategy_type else 1.01)
            
            return self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange='NFO',
                product=self.kite.PRODUCT_MIS,
                order_type=self.kite.ORDER_TYPE_LIMIT,
                price=limit_price,
                validity=self.kite.VALIDITY_DAY,
                tradingsymbol=self._get_instrument_token(
                    'CE' if strategy_type == 'STRADDLE' else 'PE',
                    expiry,
                    strike
                ),
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
