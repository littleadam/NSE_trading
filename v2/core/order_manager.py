%%writefile /content/core/order_manager.py
import logging
from datetime import datetime
from kiteconnect import KiteConnect

logger = logging.getLogger(__name__)

class OrderManager:
    def __init__(self, kite_client, config, safeguards):
        self.kite = kite_client
        self.config = config
        self.safeguards = safeguards
        self.order_cache = {}

    def place_sell_order(self, symbol, quantity):
        """Place sell order with full validation"""
        try:
            if not self._validate_order_params(symbol, quantity):
                return None

            if self._check_existing_order(symbol, 'SELL'):
                logger.warning(f"Duplicate sell order prevented for {symbol}")
                return None

            self.safeguards.check_margin_requirement(symbol, quantity, 'SELL')
            
            order_id = self.kite.place_order(
                variety=KiteConnect.VARIETY_REGULAR,
                exchange=self.config['exchange'],
                tradingsymbol=symbol,
                transaction_type=KiteConnect.TRANSACTION_TYPE_SELL,
                quantity=quantity,
                product=self.config['product_type'],
                order_type=KiteConnect.ORDER_TYPE_LIMIT,
                price=self._calculate_limit_price(symbol, 'SELL'),
                validity=KiteConnect.VALIDITY_DAY
            )
            
            self._record_order(order_id, symbol, 'SELL', quantity)
            logger.info(f"Sell order placed: {order_id} for {symbol}")
            return order_id
            
        except Exception as e:
            logger.error(f"Sell order failed: {str(e)}")
            self.safeguards.record_error()
            return None

    def place_buy_order(self, symbol, quantity):
        """Place buy order with full validation"""
        try:
            if not self._validate_order_params(symbol, quantity):
                return None

            if self._check_existing_order(symbol, 'BUY'):
                logger.warning(f"Duplicate buy order prevented for {symbol}")
                return None

            self.safeguards.check_margin_requirement(symbol, quantity, 'BUY')
            
            order_id = self.kite.place_order(
                variety=KiteConnect.VARIETY_REGULAR,
                exchange=self.config['exchange'],
                tradingsymbol=symbol,
                transaction_type=KiteConnect.TRANSACTION_TYPE_BUY,
                quantity=quantity,
                product=self.config['product_type'],
                order_type=KiteConnect.ORDER_TYPE_LIMIT,
                price=self._calculate_limit_price(symbol, 'BUY'),
                validity=KiteConnect.VALIDITY_DAY
            )
            
            self._record_order(order_id, symbol, 'BUY', quantity)
            logger.info(f"Buy order placed: {order_id} for {symbol}")
            return order_id
            
        except Exception as e:
            logger.error(f"Buy order failed: {str(e)}")
            self.safeguards.record_error()
            return None

    def place_sl_order(self, symbol, quantity, trigger_price):
        """Place stop loss order with validation"""
        try:
            if not self._validate_order_params(symbol, quantity):
                return None

            order_id = self.kite.place_order(
                variety=KiteConnect.VARIETY_STOPLOSS,
                exchange=self.config['exchange'],
                tradingsymbol=symbol,
                transaction_type=KiteConnect.TRANSACTION_TYPE_BUY,
                quantity=quantity,
                product=self.config['product_type'],
                order_type=KiteConnect.ORDER_TYPE_SL,
                price=round(trigger_price * 0.98, 1),
                trigger_price=round(trigger_price, 1),
                validity=KiteConnect.VALIDITY_DAY
            )
            
            self._record_order(order_id, symbol, 'SL', quantity)
            logger.info(f"SL order placed: {order_id} for {symbol}")
            return order_id
            
        except Exception as e:
            logger.error(f"SL order failed: {str(e)}")
            self.safeguards.record_error()
            return None

    def _calculate_limit_price(self, symbol, action):
        """Calculate limit price based on LTP and action"""
        ltp = self.kite.ltp(f"NFO:{symbol}")[f"NFO:{symbol}"]['last_price']
        return round(ltp * 0.95 if action == 'SELL' else ltp * 1.05, 1)

    def _validate_order_params(self, symbol, quantity):
        """Validate order parameters before placement"""
        if quantity % self.config['lot_size'] != 0:
            logger.error(f"Invalid lot size: {quantity} for {symbol}")
            return False
            
        if not symbol.endswith(('CE', 'PE')):
            logger.error(f"Invalid symbol format: {symbol}")
            return False
            
        return True

    def _check_existing_order(self, symbol, order_type):
        """Check for duplicate pending orders"""
        for order in self.kite.orders():
            if (order['tradingsymbol'] == symbol and
                order['transaction_type'] == order_type and
                order['status'] in ['OPEN', 'TRIGGER PENDING']):
                return True
        return False

    def _record_order(self, order_id, symbol, order_type, quantity):
        """Cache order details for tracking"""
        self.order_cache[order_id] = {
            'timestamp': datetime.now().isoformat(),
            'symbol': symbol,
            'type': order_type,
            'quantity': quantity,
            'status': 'PENDING'
        }

    def cancel_order(self, order_id):
        """Cancel pending order"""
        try:
            self.kite.cancel_order(
                variety=KiteConnect.VARIETY_REGULAR,
                order_id=order_id
            )
            logger.info(f"Cancelled order: {order_id}")
            return True
        except Exception as e:
            logger.error(f"Cancel failed: {str(e)}")
            return False

    def cleanup_pending_orders(self):
        """Cleanup all pending orders"""
        count = 0
        for order in self.kite.orders():
            if order['status'] in ['OPEN', 'TRIGGER PENDING']:
                if self.cancel_order(order['order_id']):
                    count += 1
        logger.info(f"Cleaned up {count} pending orders")
