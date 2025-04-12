# risk_manager.py
import logging
import time
from typing import Dict, List
from kiteconnect import KiteConnect
from config import Config
from utils.helpers import retry_api_call
from utils.position_tracker import PositionTracker  # Updated import

logger = logging.getLogger(__name__)

class RiskManager:
    def __init__(self, kite: KiteConnect):
        self.kite = kite
        self.position_tracker = PositionTracker(kite)  # Use consolidated tracker
        
        # Risk parameters from config
        self.profit_threshold = Config.PROFIT_POINTS * Config.LOT_SIZE
        self.portfolio_loss_threshold = Config.SHUTDOWN_LOSS
        self.position_stoploss = Config.POSITION_STOPLOSS
        self.max_retries = 3
        self.order_retry_delay = 2

    @retry_api_call(max_retries=3, backoff=1)
    def check_shutdown_triggers(self) -> bool:
        """Check all risk management triggers with position sync"""
        self.position_tracker.update_positions()
        
        try:
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
        """Check total profit across all positions"""
        total_pnl = sum(p['unrealized_pnl'] for p in positions)
        return total_pnl >= self.profit_threshold

    def _portfolio_loss_breached(self, margins: Dict) -> bool:
        """Check unrealized portfolio loss percentage"""
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
        """Check individual position stop losses in points"""
        for position in positions:
            if position['unrealized_pnl'] < 0:
                loss_points = abs(position['unrealized_pnl']) / (Config.LOT_SIZE * position['quantity'])
                if loss_points >= self.position_stoploss:
                    logger.warning(f"Position SL hit: {position['symbol']} ({loss_points}pts)")
                    return True
        return False

    @retry_api_call(max_retries=3, backoff=2)
    def execute_emergency_shutdown(self) -> None:
        """Close all positions with fallback to limit orders"""
        logger.critical("Initiating emergency shutdown sequence")
        
        positions = self.position_tracker.get_positions()
        for position in positions:
            if position['quantity'] != 0:
                self._close_position(position)
                
        logger.info("Emergency shutdown completed")

    def _close_position(self, position: Dict) -> None:
        """Close position with market order fallback to limit"""
        transaction = self.kite.TRANSACTION_TYPE_BUY if position['quantity'] < 0 \
                      else self.kite.TRANSACTION_TYPE_SELL
        quantity = abs(position['quantity'])
        
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
            
        except Exception as e:
            logger.error(f"Market order failed: {str(e)}, falling back to limit")
            self._place_limit_order(position, transaction, quantity)

    def _place_limit_order(self, position: Dict, transaction: str, quantity: int) -> None:
        """Place limit order with price calculation"""
        try:
            ltp = self.kite.ltp(f"NFO:{position['symbol']}")[f"NFO:{position['symbol']}"]['last_price']
            price = ltp * 0.95 if transaction == self.kite.SELL else ltp * 1.05
            
            order_id = self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange='NFO',
                tradingsymbol=position['symbol'],
                transaction_type=transaction,
                quantity=quantity,
                product=self.kite.PRODUCT_MIS,
                order_type=self.kite.ORDER_TYPE_LIMIT,
                price=round(price, 1)
            )
            logger.info(f"Limit order placed: {order_id}")
            
        except Exception as e:
            logger.critical(f"Limit order fallback failed: {str(e)}")
            raise
