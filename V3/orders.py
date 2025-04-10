%%writefile orders.py
from kiteconnect import KiteConnect
from config import API_KEY, ACCESS_TOKEN
from tenacity import retry, stop_after_attempt, wait_exponential
import logging

class OrderManager:
    def __init__(self):
        self.kite = KiteConnect(api_key=API_KEY)
        self.kite.set_access_token(ACCESS_TOKEN)
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def place_order(self, transaction_type, instrument, quantity, order_type, product='MIS', price=None):
        try:
            order_id = self.kite.place_order(
                tradingsymbol=instrument['tradingsymbol'],
                exchange=instrument['exchange'],
                transaction_type=transaction_type,
                quantity=quantity,
                order_type=order_type,
                product=product,
                price=price,
                validity='DAY',
                tag=f"STRATEGY_{instrument['instrument_type']}"
            )
            logging.info(f"Order placed: {order_id}")
            return order_id
        except Exception as e:
            logging.error(f"Order failed: {str(e)}")
            raise  # Let tenacity handle retries
    
    def modify_order(self, order_id, price):
        try:
            modified_id = self.kite.modify_order(
                order_id=order_id,
                price=price
            )
            return modified_id
        except Exception as e:
            logging.error(f"Order modification failed: {str(e)}")
            return None
