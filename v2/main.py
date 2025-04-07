%%writefile /content/main.py
import logging
import time
from kiteconnect import KiteConnect
from core.trade_manager import TradeManager
from config import settings
from utils.logger import configure_logger
from pyngrok import ngrok

logger = configure_logger('main')

def initialize_trading():
    # Start ngrok tunnel
    tunnel = ngrok.connect(8000)
    logger.info(f"WebSocket tunnel created: {tunnel.public_url}")
    
    # Initialize Kite Connect
    kite = KiteConnect(api_key=settings.API_CREDENTIALS['api_key'])
    kite.set_access_token(settings.API_CREDENTIALS['access_token'])
    
    # Create manager instance
    return TradeManager(kite, settings.TRADE_CONFIG)

def main():
    try:
        manager = initialize_trading()
        logger.info("Starting main trading loop")
        manager.start()
    except KeyboardInterrupt:
        logger.info("User requested shutdown")
    except Exception as e:
        logger.critical(f"Fatal error: {str(e)}", exc_info=True)
    finally:
        ngrok.kill()
        logger.info("Application shutdown complete")

if __name__ == "__main__":
    main()
