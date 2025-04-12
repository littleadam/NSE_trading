import logging
from config import LOT_SIZE, PROFIT_POINTS, SHUTDOWN_LOSS

logger = logging.getLogger(__name__)

class RiskManager:
    def __init__(self, kite):
        self.kite = kite
        self.profit_threshold = PROFIT_POINTS * LOT_SIZE
        self.loss_threshold = SHUTDOWN_LOSS
        self.lot_size = LOT_SIZE

    def check_shutdown_triggers(self):
        """Check all risk management triggers"""
        try:
            positions = self.kite.positions().get('net', [])
            
            if self._profit_target_reached(positions):
                logger.warning("Profit target triggered shutdown")
                return True
                
            if self._portfolio_loss_breached():
                logger.warning("Portfolio loss threshold breached")
                return True
                
            if self._position_stoploss_hit(positions):
                logger.warning("Position stop loss triggered")
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"Risk check failed: {str(e)}")
            return True  # Fail-safe shutdown

    def _profit_target_reached(self, positions):
        """Check total profit across all positions"""
        total_pnl = sum(p['realised'] + p['unrealised'] for p in positions)
        return total_pnl >= self.profit_threshold

    def _portfolio_loss_breached(self):
        """Check unrealized portfolio loss percentage"""
        try:
            equity = self.kite.margins()['equity']
            unrealized = sum(p['unrealised'] for p in self.kite.positions()['net'])
            
            if unrealized >= 0:
                return False
                
            total_equity = equity['available']['cash'] + equity['used']['total']
            if total_equity <= 0:
                return False
                
            loss_pct = (abs(unrealized) / total_equity) * 100
            return loss_pct >= self.loss_threshold
            
        except KeyError as e:
            logger.error(f"Margin data error: {str(e)}")
            return False

    def _position_stoploss_hit(self, positions):
        """Check individual position stop losses"""
        for position in positions:
            if position['unrealised'] < 0:
                loss_points = abs(position['unrealised']) / self.lot_size
                if loss_points >= PROFIT_POINTS:
                    logger.info(f"Stop loss hit: {position['tradingsymbol']}")
                    return True
        return False

    def execute_emergency_shutdown(self):
        """Close all positions immediately"""
        try:
            for position in self.kite.positions()['net']:
                if abs(position['quantity']) > 0:
                    self._close_position(position)
                    
            logger.info("Emergency shutdown completed")
            
        except Exception as e:
            logger.error(f"Shutdown failed: {str(e)}")
            raise

    def _close_position(self, position):
        """Close individual position with market order"""
        transaction = self.kite.BUY if position['quantity'] < 0 else self.kite.SELL
        self.kite.place_order(
            variety=self.kite.VARIETY_REGULAR,
            exchange='NFO',
            tradingsymbol=position['tradingsymbol'],
            transaction_type=transaction,
            quantity=abs(position['quantity']),
            product=self.kite.PRODUCT_MIS,
            order_type=self.kite.ORDER_TYPE_MARKET
        )
