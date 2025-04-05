from config.settings import API_CREDENTIALS, TRADE_CONFIG
from core.trade_manager import TradeManager
from utils.logger import configure_logger
import logging

def main():
    print("=== Starting Ironfly Trading System ===")
    configure_logger('main')
    
    try:
        print("Initializing components...")
        manager = TradeManager(
            API_CREDENTIALS['api_key'],
            API_CREDENTIALS['access_token']
        )
        print("Components initialized successfully")
        
        print("Starting main trading loop...")
        manager.start()
        
    except Exception as e:
        logging.error(f"Fatal error: {str(e)}")
        print("!!! SYSTEM CRASHED !!!")
        
    print("=== Trading System Stopped ===")

if __name__ == "__main__":
    main()
