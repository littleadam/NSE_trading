# core/risk_manager.py
import logging
import time
from typing import Dict, List
from kiteconnect import KiteConnect
from config import Config
from utils.helpers import retry_api_call
from utils.position_tracker import PositionTracker

logger = logging.getLogger(__name__)

class RiskManager:
    def __init__(self, kite: KiteConnect):
        self.kite = kite
        self.position_tracker = PositionTracker(kite)
        
        # Initialize risk parameters with explicit config references
        self.profit_threshold = Config.PROFIT_POINTS * Config.LOT_SIZE
        self.portfolio_loss_threshold = Config.SHUTDOWN_LOSS
        self.position_stoploss = Config.POSITION_STOPLOSS
        self.max_retries = 3
        self.order_retry_delay = 2
        self.rollover_days_threshold = Config.ROLLOVER_DAYS_THRESHOLD

    @retry_api_call(max_retries=3, backoff=1)
    def check_shutdown_triggers(self) -> bool:
        """Enhanced risk checks with position synchronization"""
        try:
            self.position_tracker.update_positions()
            positions = self.position_tracker.get_positions()
            margins = self.kite.margins()
            
            triggers = [
                self._profit_target_reached(positions),
                self._portfolio_loss_breached(margins),
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
        """Calculate profit using lot size from config"""
        total_pnl = sum(p['unrealized_pnl'] for p in positions)
        return total_pnl >= self.profit_threshold

    def _portfolio_loss_breached(self, margins: Dict) -> bool:
        """Improved margin calculation with error handling"""
        try:
            equity = margins['equity']['net']
            unrealized = sum(p['unrealized_pnl'] for p in self.position_tracker.get_positions())
            
            if unrealized >= 0:
                return False
                
            total_equity = equity['available']['cash'] + equity['utilised']['total']
            if total_equity <= 0:
                return False
                
            loss_pct = (abs(unrealized) / total_equity) * 100
            return loss_pct >= self.portfolio_loss_threshold
            
        except KeyError as e:
            logger.error(f"Margin data error: {str(e)}")
            return False

    def _position_stoploss_hit(self, positions: List[Dict]) -> bool:
        """Position SL with configurable points"""
        for position in positions:
            if position['unrealized_pnl'] < 0:
                loss_points = abs(position['unrealized_pnl']) / (Config.LOT_SIZE * position['quantity'])
                if loss_points >= self.position_stoploss:
                    logger.warning(f"Position SL hit: {position['symbol']} ({loss_points}pts)")
                    return True
        return False

    @retry_api_call(max_retries=3, backoff=2)
    def execute_emergency_shutdown(self) -> None:
        """Enhanced shutdown with batch cancellation and fallbacks"""
        logger.critical("Initiating emergency shutdown sequence")
        
        # Cancel all pending orders first
        self._cancel_all_pending_orders()
        
        # Close positions with improved error handling
        positions = self.position_tracker.get_positions()
        for position in positions:
            if position['quantity'] != 0:
                self._close_position(position)
                
        logger.info("Emergency shutdown completed")

    def _cancel_all_pending_orders(self) -> None:
        """Batch cancel all open orders"""
        try:
            orders = self.kite.orders()
            for order in orders:
                if order['status'] in ['OPEN', 'TRIGGER PENDING']:
                    self.kite.cancel_order(
                        order_id=order['order_id'],
                        variety=order['variety']
                    )
                    logger.info(f"Cancelled pending order: {order['order_id']}")
                    time.sleep(0.1)  # Rate limit protection
        except Exception as e:
            logger.error(f"Order cancellation failed: {str(e)}")

    def _close_position(self, position: Dict) -> None:
        """Improved position closing with multiple fallbacks"""
        transaction = self.kite.TRANSACTION_TYPE_BUY if position['quantity'] < 0 \
                      else self.kite.TRANSACTION_TYPE_SELL
        quantity = abs(position['quantity'])
        
        attempts = 0
        while attempts < 3:
            try:
                # Attempt market order first
                order_id = self.kite.place_order(
                    variety=self.kite.VARIETY_REGULAR,
                    exchange='NFO',
                    tradingsymbol=position['symbol'],
                    transaction_type=transaction,
                    quantity=quantity,
                    product=self.kite.PRODUCT_MIS,
                    order_type=self.kite.ORDER_TYPE_MARKET
                )
                logger.info(f"Market order placed: {order_id}")
                return
                
            except Exception as e:
                logger.error(f"Market order failed: {str(e)}, attempt {attempts+1}/3")
                attempts += 1
                time.sleep(1)
        
        # Final fallback to limit order
        self._place_limit_order(position, transaction, quantity)

    def _place_limit_order(self, position: Dict, transaction: str, quantity: int) -> None:
        """Limit order placement with price validation"""
        try:
            ltp = self.kite.ltp(f"NFO:{position['symbol']}")[f"NFO:{position['symbol']}"]['last_price']
            price = round(ltp * 0.95 if transaction == self.kite.SELL else ltp * 1.05, 1)
            
            order_id = self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange='NFO',
                tradingsymbol=position['symbol'],
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
