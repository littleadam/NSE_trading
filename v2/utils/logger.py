%%writefile /content/utils/logger.py
import logging
import os
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime
from config import settings

def configure_logger(name):
    """Configure multi-handler logger with settings integration"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Create log directory structure
    os.makedirs('logs', exist_ok=True)
    
    # 1. File Handler (Daily Rotation)
    file_handler = TimedRotatingFileHandler(
        filename='logs/trading_system.log',
        when='midnight',
        interval=1,
        backupCount=7,
        encoding='utf-8'
    )
    file_formatter = logging.Formatter(
        '%(asctime)s | %(name)s | %(levelname)s | %(message)s'
    )
    file_handler.setFormatter(file_formatter)
    
    # 2. Console Handler (Market Hours Formatting)
    console_handler = logging.StreamHandler()
    
    class MarketHoursFormatter(logging.Formatter):
        def format(self, record):
            now = datetime.now().strftime('%H:%M:%S')
            market_open = settings.TRADE_CONFIG['trading_hours']['start']
            market_close = settings.TRADE_CONFIG['trading_hours']['end']
            status = "🟢" if market_open <= now <= market_close else "🔴"
            return f"{status} {now} | {record.levelname} | {record.message}"
    
    console_handler.setFormatter(MarketHoursFormatter())
    
    # 3. Error Handler (Separate Error Log)
    error_handler = logging.FileHandler('logs/errors.log')
    error_formatter = logging.Formatter(
        '%(asctime)s | %(name)s | %(levelname)s | %(pathname)s:%(lineno)d | %(message)s'
    )
    error_handler.setFormatter(error_formatter)
    error_handler.setLevel(logging.WARNING)
    
    # Add all handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.addHandler(error_handler)
    
    # Startup log entry
    logger.info(
        f"Logger initialized | "
        f"Market Hours: {settings.TRADE_CONFIG['trading_hours']['start']}-"
        f"{settings.TRADE_CONFIG['trading_hours']['end']} | "
        f"Trading Days: {', '.join(settings.TRADE_CONFIG['weekly_schedule']['days'])}"
    )
    
    return logger
