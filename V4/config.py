%%writefile config.py
from dotenv import load_dotenv
import os
from typing import Dict, Any

load_dotenv()

class Config:
    """Central configuration class with validation"""
    
    def __init__(self):
        self.SPECIAL_DAYS = os.getenv("SPECIAL_DAYS", "2023-12-23,2024-01-20").split(",")
        self.HOLIDAYS = os.getenv("HOLIDAYS", "2025-10-02,2025-08-15").split(",")
        self.HEDGE_CLOSING_BUFFER = int(os.getenv("HEDGE_CLOSING_BUFFER", "50"))
        self._validate_credentials()
        self._load_parameters()
        self._validate_values()

    def _validate_credentials(self):
        required = ["Z_API_KEY", "Z_API_SECRET", "Z_USER_ID"]
        missing = [var for var in required if not os.getenv(var)]
        if missing:
            raise EnvironmentError(f"Missing required variables: {', '.join(missing)}")

    def _load_parameters(self):
        # API Configuration
        self.API_KEY = os.getenv("Z_API_KEY")
        self.API_SECRET = os.getenv("Z_API_SECRET")
        self.USER_ID = os.getenv("Z_USER_ID")
        
        # Trading Parameters
        self.LOT_SIZE = int(os.getenv("LOT_SIZE", "75"))
        self.MARGIN_PER_LOT = int(os.getenv("MARGIN_PER_LOT", "120000"))
        self.POINT_VALUE = int(os.getenv("POINT_VALUE", "75"))
        self.STRIKE_ROUNDING = int(os.getenv("STRIKE_ROUNDING", "50"))
        
        # Strategy Parameters
        self.BIAS = int(os.getenv("BIAS", "0"))
        self.ADJACENCY_GAP = int(os.getenv("ADJACENCY_GAP", "50"))
        self.STRADDLE_FLAG = os.getenv("STRADDLE_FLAG", "True").lower() == 'true'
        self.STRANGLE_FLAG = os.getenv("STRANGLE_FLAG", "False").lower() == 'true'
        self.FAR_SELL_ADD = os.getenv("FAR_SELL_ADD", "True").lower() == 'true'
        self.BUY_HEDGE = os.getenv("BUY_HEDGE", "True").lower() == 'true'
        
        # Risk Management
        self.HEDGE_LOSS_THRESHOLD = float(os.getenv("HEDGE_LOSS_THRESHOLD", "0.25"))
        self.SHUTDOWN_LOSS = float(os.getenv("SHUTDOWN_LOSS", "0.125"))
        self.PROFIT_POINTS = int(os.getenv("PROFIT_POINTS", "250"))
        
        # Time Parameters
        self.CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "300"))
        self.TRADING_HOURS = {
            "start": os.getenv("TRADING_HOURS_START", "09:15"),
            "end": os.getenv("TRADING_HOURS_END", "15:30")
        }
        self.EXPIRY_MONTHS = int(os.getenv("EXPIRY_MONTHS", "3"))
        self.STRANGLE_DISTANCE = int(os.getenv("STRANGLE_DISTANCE", "1000"))
        self.EXPIRY_ROLLOVER_HOUR = int(os.getenv("EXPIRY_ROLLOVER_HOUR", "15"))

    def _validate_values(self):
        if self.LOT_SIZE <= 0:
            raise ValueError("LOT_SIZE must be positive")
        if self.MARGIN_PER_LOT <= 0:
            raise ValueError("MARGIN_PER_LOT must be positive")
        if not 0 <= self.HEDGE_LOSS_THRESHOLD <= 1:
            raise ValueError("HEDGE_LOSS_THRESHOLD must be 0-1")

config = Config()
