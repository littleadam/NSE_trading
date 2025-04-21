import os
import sys
import logging
import time
import datetime
import schedule
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import modules
from auth.kite_auth import KiteAuth
from core.streaming import StreamingService
from core.order_manager import OrderManager
from core.expiry_manager import ExpiryManager
from core.risk_manager import RiskManager
from core.strategy import Strategy
from utils.logger import Logger
from utils.helpers import Helpers
from config import Config

def initialize_modules():
    """
    Initialize all modules required for the application
    
    Returns:
        Tuple of (kite, streaming_service, strategy)
    """
    # Load configuration
    config = Config()
    
    # Initialize logger
    logger_instance = Logger(config)
    logger = logger_instance.get_logger()
    
    logger.info("Main: Initializing application")
    
    # Initialize Kite authentication
    kite_auth = KiteAuth(logger)
    kite = kite_auth.authenticate()
    
    if not kite:
        logger.error("Main: Failed to authenticate with Kite")
        sys.exit(1)
    
    logger.info("Main: Authentication successful")
    
    # Initialize order manager
    order_manager = OrderManager(kite, logger, config)
    
    # Initialize expiry manager
    expiry_manager = ExpiryManager(kite, logger, config)
    
    # Initialize risk manager
    risk_manager = RiskManager(kite, logger, config, order_manager)
    
    # Initialize helpers
    helpers = Helpers(kite, logger)
    
    # Initialize streaming service
    streaming_service = StreamingService(kite, logger)
    
    # Initialize strategy
    strategy = Strategy(
        kite, 
        logger, 
        config, 
        order_manager, 
        expiry_manager, 
        risk_manager, 
        streaming_service
    )
    
    logger.info("Main: All modules initialized successfully")
    
    return kite, streaming_service, strategy

def run_strategy(strategy, logger):
    """
    Run the strategy once
    
    Args:
        strategy: Strategy instance
        logger: Logger instance
    """
    logger.log_execution_start()
    
    try:
        strategy.execute()
    except Exception as e:
        logger.error(f"Main: Error executing strategy: {str(e)}")
    
    logger.log_execution_end()

def schedule_strategy(strategy, logger, config):
    """
    Schedule strategy execution
    
    Args:
        strategy: Strategy instance
        logger: Logger instance
        config: Configuration instance
    """
    logger.info(f"Main: Scheduling strategy to run every {config.run_interval} minutes")
    
    # Schedule strategy to run every X minutes
    schedule.every(config.run_interval).minutes.do(run_strategy, strategy=strategy, logger=logger)
    
    # Run immediately for the first time
    run_strategy(strategy, logger)
    
    # Keep running until end time
    while True:
        now = datetime.datetime.now().time()
        end_time = datetime.datetime.strptime(config.end_time, "%H:%M:%S").time()
        
        if now > end_time:
            logger.info("Main: End time reached, stopping application")
            break
        
        schedule.run_pending()
        time.sleep(1)

def main():
    """
    Main entry point for the application
    """
    # Create logs directory if it doesn't exist
    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs'), exist_ok=True)
    
    # Initialize modules
    kite, streaming_service, strategy = initialize_modules()
    
    # Get logger and config
    config = Config()
    logger = logging.getLogger('nse_trading')
    
    # Start streaming service
    if not streaming_service.start():
        logger.error("Main: Failed to start streaming service")
        sys.exit(1)
    
    try:
        # Schedule and run strategy
        schedule_strategy(strategy, logger, config)
    except KeyboardInterrupt:
        logger.info("Main: Application stopped by user")
    except Exception as e:
        logger.error(f"Main: Unexpected error: {str(e)}")
    finally:
        # Stop streaming service
        streaming_service.stop()
        logger.info("Main: Application shutdown complete")

if __name__ == "__main__":
    main()
