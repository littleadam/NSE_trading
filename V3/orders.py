%%writefile orders.py
from kiteconnect import KiteConnect
from config import API_KEY, ACCESS_TOKEN
import logging

class OrderManager:
    def __init__(self):
        self.kite = KiteConnect(api_key=API_KEY)
        self.kite.set_access_token(ACCESS_TOKEN)
    
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
            if order_type == 'MARKET':
                ltp = self.kite.ltp(instrument['tradingsymbol'])[instrument['tradingsymbol']]['last_price']
                return self.place_order(transaction_type, instrument, quantity, 'LIMIT', product, ltp)
            return None
    
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
