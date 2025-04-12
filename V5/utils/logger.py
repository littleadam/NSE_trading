# utils/logger.py
import logging
import sys
from functools import wraps
from datetime import datetime
from logging.handlers import RotatingFileHandler

# Configure root logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

formatter = logging.Formatter(
    '%(asctime)s | %(name)s | %(funcName)s:%(lineno)d | %(levelname)s | %(message)s'
)

# File handler with rotation
file_handler = RotatingFileHandler(
    'trading_app.log',
    maxBytes=10*1024*1024,  # 10 MB
    backupCount=5,
    encoding='utf-8'
)
file_handler.setFormatter(formatter)

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

def log_function(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger.info(f"Function {func.__name__} started with args: {args}, kwargs: {kwargs}")
        try:
            result = func(*args, **kwargs)
            logger.info(f"Function {func.__name__} completed successfully")
            return result
        except Exception as e:
            logger.error(f"Function {func.__name__} failed with error: {str(e)}", exc_info=True)
            raise
    return wrapper

class DecisionLogger:
    @staticmethod
    def log_decision(decision_data):
        logger.info(f"TRADING DECISION: {decision_data}")
