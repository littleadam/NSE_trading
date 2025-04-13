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
        
        # Initialize risk parameters with validation
        if not hasattr(Config, 'LOT_SIZE'):
            raise ValueError("Missing required config: LOT_SIZE")
            
        self.profit_threshold = Config.PROFIT_POINTS * Config.LOT_SIZE * 0.05  # 0.05 is Nifty point value
        self.portfolio_loss_threshold = Config.SHUTDOWN_LOSS
        self.position_stoploss = Config.POSITION_STOPLOSS
        self.max_retries = 3
        self.order_retry_delay = 2

    @retry_api_call(max_retries=3, backoff=1)
    def check_shutdown_triggers(self) -> bool:
        """Comprehensive risk checks with position synchronization and validation"""
        try:
            # Update positions only if older than 10 seconds
            if (datetime.now() - self.last_position_update) > timedelta(seconds=10):
                self.position_tracker.update_positions()
                self.last_position_update = datetime.now()

            positions = self.position_tracker.get_positions()
            margins = self._safe_get_margins()
            
            triggers = [
                self._profit_target_reached(positions),
                self._portfolio_loss_breached(margins, positions),
                self._position_stoploss_hit(positions)
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
        return total_pnl >= self.profit_threshold

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
            return loss_pct >= self.portfolio_loss_threshold
            
        except (KeyError, TypeError, ZeroDivisionError) as e:
            logger.error(f"Margin calculation error: {str(e)}")
            return False

    def _position_stoploss_hit(self, positions: List[Dict]) -> bool:
        """Position SL with configurable points and validation"""
        for position in positions:
            if position.get('unrealized_pnl', 0) < 0:
                quantity = abs(position.get('quantity', 0))
                loss = abs(position['unrealized_pnl'])
                loss_points = loss / (Config.LOT_SIZE * quantity) if quantity > 0 else 0
                
                if loss_points >= self.position_stoploss:
                    logger.warning(f"Position SL hit: {position.get('symbol')} ({loss_points:.1f}pts)")
                    return True
        return False

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
            price = round(ltp * 0.95 if transaction == self.kite.SELL else ltp * 1.05, 1)
            
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
