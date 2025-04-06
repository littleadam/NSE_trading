from config.settings import API_CREDENTIALS
from core.trade_manager import TradeManager
from utils.logger import configure_logger
import logging

def main():
    print("=== Starting Ironfly Trading System ===")
    configure_logger('main')
    
    try:
        print("Initializing Trade Manager...")
        manager = TradeManager(
            API_CREDENTIALS['api_key'],
            API_CREDENTIALS['access_token']
        )
        
        print("Starting trading loop...")
        manager.start()
        
    except Exception as e:
        logging.critical(f"Fatal error: {str(e)}", exc_info=True)
        print("!!! SYSTEM CRASHED !!!")
        
    print("=== Trading System Stopped ===")

if __name__ == "__main__":
    main()
