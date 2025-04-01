# kite_utils.py
import logging
import csv
from datetime import datetime
from kiteconnect import KiteConnect
from pathlib import Path
from typing import Dict, List
from config import Config

class KiteManager:
    def __init__(self, config: Config):
        self.config = config
        self.kite = KiteConnect(api_key=config.API_KEY)
        self.kite.set_access_token(config.ACCESS_TOKEN)
        self._setup_logging()
        
    def _setup_logging(self):
        Path(self.config.LOG_DIR).mkdir(exist_ok=True)
        log_file = Path(self.config.LOG_DIR) / f"strategy_execution_{datetime.now().date()}.log"
        
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

    def _log_order(self, order_details: Dict):
        """Log order details to CSV file"""
        with open('order_history.csv', 'a', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=order_details.keys())
            if csvfile.tell() == 0:
                writer.writeheader()
            writer.writerow(order_details)

    def _get_funds(self):
        try:
            return self.kite.margins()['equity']['available']['live_balance']
        except Exception as e:
            self.logger.error(f"Failed to fetch funds: {str(e)}")
            return None

    def place_market_order(self, tradingsymbol: str, exchange: str, 
                         transaction_type: str, quantity: int, reason: str) -> Dict:
        """Enhanced order placement with logging"""
        order_details = {
            'timestamp': datetime.now().isoformat(),
            'symbol': tradingsymbol,
            'exchange': exchange,
            'type': transaction_type,
            'quantity': quantity,
            'reason': reason,
            'status': 'PENDING',
            'error': None,
            'funds_before': None,
            'funds_after': None,
            'order_id': None
        }

        try:
            order_details['funds_before'] = self._get_funds()
            order_id = self.kite.place_order(
                variety=KiteConnect.VARIETY_REGULAR,
                exchange=exchange,
                tradingsymbol=tradingsymbol,
                transaction_type=transaction_type,
                quantity=quantity,
                order_type=KiteConnect.ORDER_TYPE_MARKET,
                product=KiteConnect.PRODUCT_NRML
            )
            order_details.update({
                'status': 'SUCCESS',
                'order_id': order_id,
                'funds_after': self._get_funds()
            })
            self.logger.info(f"Order {order_id} placed successfully for {tradingsymbol}")
        except Exception as e:
            order_details.update({
                'status': 'FAILED',
                'error': str(e)
            })
            self.logger.error(f"Order failed for {tradingsymbol}: {str(e)}")
        
        self._log_order(order_details)
        return order_details

    def get_positions(self) -> Dict:
        return self.kite.positions()
    
    def get_orders(self) -> List[Dict]:
        return self.kite.orders()
    
    def place_sl_order(self, tradingsymbol: str, exchange: str, 
                      transaction_type: str, quantity: int, trigger_price: float):
        try:
            order_id = self.kite.place_order(
                variety=KiteConnect.VARIETY_REGULAR,
                exchange=exchange,
                tradingsymbol=tradingsymbol,
                transaction_type=transaction_type,
                quantity=quantity,
                order_type=KiteConnect.ORDER_TYPE_SL,
                product=KiteConnect.PRODUCT_NRML,
                trigger_price=trigger_price
            )
            logging.info(f"SL Order placed for {tradingsymbol}, ID: {order_id}")
            return order_id
        except Exception as e:
            logging.error(f"SL Order placement failed: {e}")
            raise

    def get_ltp(self, instruments: List[Dict]) -> Dict:
        return self.kite.ltp(instruments)# Add similar enhanced logging for place_sl_order and other methods# ... (rest of KiteManager methods from previous version)
