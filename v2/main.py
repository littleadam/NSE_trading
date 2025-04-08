%%writefile /content/main.py
import logging
import time
from kiteconnect import KiteConnect
from core.trade_manager import TradeManager
from config import settings
from utils.logger import configure_logger
from pyngrok import ngrok

logger = configure_logger('main')

def configure_ngrok():
    """Set up Ngrok tunnel with authentication"""
    try:
        conf.get_default().auth_token = settings.NGROK_CONFIG['auth_token']
        conf.get_default().region = settings.NGROK_CONFIG['region']
        tunnel = ngrok.connect(
            settings.NGROK_CONFIG['port'], 
            proto="http",
            bind_tls=True
        )
        logger.info(f"Ngrok tunnel established at: {tunnel.public_url}")
        return tunnel
    except Exception as e:
        logger.critical(f"Ngrok setup failed: {str(e)}")
        raise

def initialize_kite():
    """Initialize Kite Connect with error handling"""
    try:
        kite = KiteConnect(api_key=settings.API_CREDENTIALS['api_key'])
        kite.set_access_token(settings.API_CREDENTIALS['access_token'])
        logger.info("Kite Connect initialized successfully")
        return kite
    except Exception as e:
        logger.critical(f"Kite login failed: {str(e)}")
        raise
        
def initialize_trading():
    # Start ngrok tunnel
    ngrok config add-authtoken 2vQbN501tKymUQHcvOr1mfXCnTw_GCk3FnKDGhc2R7pHHtRZ
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
