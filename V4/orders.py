%%writefile orders.py
from kiteconnect import KiteConnect
from tenacity import retry, stop_after_attempt, wait_exponential
from config import config
from logger import setup_logger
from typing import Dict, Optional

log = setup_logger()

class OrderManager:
    def __init__(self):
        self.kite = KiteConnect(api_key=config.API_KEY)
        self.kite.set_access_token(config.API_SECRET)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def place_order(self, transaction_type: str, instrument: Dict, 
                   quantity: int, order_type: str, **kwargs) -> Optional[str]:
        """Place order with retry logic"""
        adjusted = False
        while self.position_manager.existing_position_check(
            instrument['expiry'], 
            instrument['strike'], 
            instrument['instrument_type']
       ):
            instrument['strike'] -= config.STRIKE_ROUNDING
            adjusted = True
    
        if adjusted:
            log.warning(f"Adjusted strike to {instrument['strike']} due to existing position")
            log.info(f"Placing {order_type} order: {transaction_type} {instrument['tradingsymbol']} x{quantity}")
        try:
            params = {
                'tradingsymbol': instrument['tradingsymbol'],
                'exchange': instrument['exchange'],
                'transaction_type': transaction_type,
                'quantity': quantity,
                'order_type': order_type,
                'product': kwargs.get('product', 'MIS'),
                'validity': kwargs.get('validity', 'DAY'),
                'price': kwargs.get('price'),
                'tag': kwargs.get('tag', '')
            }
            
            order_id = self.kite.place_order(**params)
            log.info(f"Order {order_id} placed successfully")
            return order_id
            
        except Exception as e:
            log.error(f"Order failed: {str(e)}")
            if order_type == 'MARKET':
                return self._place_limit_order_fallback(instrument, quantity)
            raise

    def _place_limit_order_fallback(self, instrument: Dict, quantity: int) -> Optional[str]:
        """Fallback to limit order"""
        log.info("Attempting limit order fallback")
        try:
            ltp = self.kite.ltp(instrument['tradingsymbol'])[instrument['tradingsymbol']]['last_price']
            return self.place_order(
                'SELL', 
                instrument, 
                quantity, 
                'LIMIT', 
                price=ltp
            )
        except Exception as e:
            log.error("Limit order fallback failed", exc_info=True)
            return None

    def modify_order(self, order_id: str, price: float) -> Optional[str]:
        """Modify existing order"""
        log.info(f"Modifying order {order_id} to {price}")
        try:
            modified_id = self.kite.modify_order(
                order_id=order_id,
                price=round(price, 1)
            )
            log.info(f"Order {order_id} modified successfully")
            return modified_id
        except Exception as e:
            log.error(f"Modification failed: {str(e)}")
            return None
