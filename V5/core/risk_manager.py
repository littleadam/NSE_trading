# core/risk_manager.py
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from kiteconnect import KiteConnect
from config import Config
from utils.helpers import retry_api_call
from utils.position_tracker import PositionTracker

logger = logging.getLogger(__name__)

class RiskManager:
    def __init__(self, kite: KiteConnect):
        self.kite = kite
        self.position_tracker = PositionTracker(kite)
        self.last_position_update = datetime.min
        self.last_margin_check = datetime.min
        self.margin_cache = {}
        
        # Validate required configuration
        self._validate_config()

    def _validate_config(self):
        """Ensure all required configuration parameters exist"""
        required_params = [
            'LOT_SIZE', 'PROFIT_POINTS', 'SHUTDOWN_LOSS',
            'POSITION_STOPLOSS', 'HEDGE_PREMIUM_THRESHOLD',
            'MARGIN_UTILIZATION_LIMIT'
        ]
        for param in required_params:
            if not hasattr(Config, param):
                raise ValueError(f"Missing required config: {param}")

    @retry_api_call(max_retries=3, backoff=1)
    def check_shutdown_triggers(self) -> bool:
        """Comprehensive risk checks with position synchronization and validation"""
        try:
            # Update positions if older than 10 seconds
            if (datetime.now() - self.last_position_update) > timedelta(seconds=10):
                self.position_tracker.update_positions()
                self.last_position_update = datetime.now()

            # Update margins if older than 30 seconds
            if (datetime.now() - self.last_margin_check) > timedelta(seconds=30):
                self.margin_cache = self._safe_get_margins()
                self.last_margin_check = datetime.now()

            positions = self.position_tracker.get_positions()
            
            triggers = [
                self._profit_target_reached(positions),
                self._portfolio_loss_breached(self.margin_cache, positions),
                self._position_stoploss_hit(positions),
                self._margin_utilization_breached(self.margin_cache),
                self._is_data_stale()
            ]
            
            if any(triggers):
                logger.warning(f"Shutdown triggers activated: {triggers}")
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"Risk check failed: {str(e)}", exc_info=True)
            return True  # Fail-safe shutdown

    def _profit_target_reached(self, positions: List[Dict]) -> bool:
        """Calculate profit using correct point value calculation"""
        total_pnl = sum(p.get('unrealized_pnl', 0) for p in positions)
        return total_pnl >= (Config.PROFIT_POINTS * Config.LOT_SIZE)

    def _portfolio_loss_breached(self, margins: Dict, positions: List[Dict]) -> bool:
        """Improved margin calculation with error resilience"""
        try:
            if not margins or 'equity' not in margins:
                return False
                
            equity = margins['equity'].get('net', {})
            unrealized = sum(p.get('unrealized_pnl', 0) for p in positions)
            
            if unrealized >= 0:
                return False
                
            available_cash = equity.get('available', {}).get('cash', 0)
            utilised = equity.get('utilised', {}).get('total', 0)
            total_equity = available_cash + utilised
            
            if total_equity <= 0:
                return False
                
            loss_pct = (abs(unrealized) / total_equity) * 100
            return loss_pct >= Config.SHUTDOWN_LOSS
            
        except (KeyError, TypeError, ZeroDivisionError) as e:
            logger.error(f"Margin calculation error: {str(e)}")
            return False

    def _position_stoploss_hit(self, positions: List[Dict]) -> bool:
        """Position SL with configurable points and validation"""
        for position in positions:
            try:
                quantity = abs(position.get('quantity', 0))
                if quantity == 0:
                    continue

                # Get position direction from tracker data
                is_long = position.get('transaction_type') == self.kite.TRANSACTION_TYPE_BUY
                entry_price = position.get('entry_price')
                ltp = position.get('ltp')

                if not entry_price or not ltp:
                    continue

                # Calculate loss based on position direction
                if is_long:
                    loss_points = (entry_price - ltp)
                else:
                    loss_points = (ltp - entry_price)

                if loss_points >= Config.POSITION_STOPLOSS:
                    logger.warning(
                        f"Position SL hit: {position.get('symbol')} "
                        f"({'Long' if is_long else 'Short'}) "
                        f"({loss_points:.1f}pts)"
                    )
                    return True
            except KeyError as e:
                logger.error(f"Invalid position data: {str(e)}")
                continue
        return False

    def _margin_utilization_breached(self, margins: Dict) -> bool:
        """Check margin utilization percentage"""
        try:
            if not margins or 'equity' not in margins:
                return False
                
            equity = margins['equity'].get('net', {})
            utilised = equity.get('utilised', {}).get('total', 0)
            available = equity.get('available', {}).get('cash', 0)
            total_equity = utilised + available
            
            if total_equity <= 0:
                return False
                
            margin_utilization = (utilised / total_equity) * 100
            return margin_utilization > Config.MARGIN_UTILIZATION_LIMIT
            
        except (KeyError, TypeError, ZeroDivisionError) as e:
            logger.error(f"Margin utilization check failed: {str(e)}")
            return False

    def _is_data_stale(self) -> bool:
        """Circuit breaker for stale data"""
        try:
            last_update_age = (datetime.now() - self.last_position_update).total_seconds()
            return last_update_age > 120  # 2 minutes without updates
        except Exception as e:
            logger.error(f"Stale check failed: {str(e)}")
            return True

    @retry_api_call(max_retries=3, backoff=2)
    def execute_emergency_shutdown(self) -> None:
        """Comprehensive shutdown with order cancellation and position closing"""
        logger.critical("Initiating emergency shutdown sequence")
        
        try:
            # Cancel all pending orders
            self._cancel_all_pending_orders()
            
            # Close all positions with retry logic
            positions = self.position_tracker.get_positions()
            for position in positions:
                if position.get('quantity', 0) != 0:
                    self._close_position_with_retry(position)
                    
            logger.info("Emergency shutdown completed successfully")
            
        except Exception as e:
            logger.critical(f"Shutdown failed: {str(e)}")
            raise

    def _cancel_all_pending_orders(self) -> None:
        """Batch cancel all open orders with rate limiting"""
        try:
            orders = self.kite.orders()
            for order in orders:
                if order.get('status') in ['OPEN', 'TRIGGER PENDING']:
                    self.kite.cancel_order(
                        order_id=order['order_id'],
                        variety=order.get('variety', 'regular')
                    )
                    logger.info(f"Cancelled order: {order['order_id']}")
                    time.sleep(0.2)  # Rate limit protection
        except Exception as e:
            logger.error(f"Order cancellation failed: {str(e)}")

    def _close_position_with_retry(self, position: Dict) -> None:
        """Robust position closing with multiple fallback strategies"""
        symbol = position.get('symbol')
        quantity = abs(position.get('quantity', 0))
        
        if quantity == 0:
            return

        transaction = self.kite.TRANSACTION_TYPE_BUY if position['quantity'] < 0 \
                      else self.kite.TRANSACTION_TYPE_SELL

        for attempt in range(3):
            try:
                # Try market order first
                order_id = self.kite.place_order(
                    variety=self.kite.VARIETY_REGULAR,
                    exchange='NFO',
                    tradingsymbol=symbol,
                    transaction_type=transaction,
                    quantity=quantity,
                    product=self.kite.PRODUCT_MIS,
                    order_type=self.kite.ORDER_TYPE_MARKET
                )
                logger.info(f"Market order placed: {order_id}")
                return
                
            except Exception as e:
                logger.warning(f"Market order failed ({attempt+1}/3): {str(e)}")
                if attempt == 2:
                    self._place_limit_order_fallback(symbol, transaction, quantity)
                time.sleep(1)

    def _place_limit_order_fallback(self, symbol: str, transaction: str, quantity: int) -> None:
        """Limit order fallback with price validation"""
        try:
            ltp = self.kite.ltp(f"NFO:{symbol}")[f"NFO:{symbol}"]['last_price']
            price = round(ltp * 0.95 if transaction == self.kite.TRANSACTION_TYPE_SELL else ltp * 1.05, 1)
            
            order_id = self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange='NFO',
                tradingsymbol=symbol,
                transaction_type=transaction,
                quantity=quantity,
                product=self.kite.PRODUCT_MIS,
                order_type=self.kite.ORDER_TYPE_LIMIT,
                price=price
            )
            logger.info(f"Limit order placed: {order_id}")
            
        except Exception as e:
            logger.critical(f"Limit order fallback failed: {str(e)}")
            raise

    def _safe_get_margins(self) -> Dict:
        """Safe margin retrieval with error handling"""
        try:
            return self.kite.margins()
        except Exception as e:
            logger.error(f"Margin fetch failed: {str(e)}")
            return {}
