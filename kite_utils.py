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

    # ... (rest of KiteManager methods from previous version)
