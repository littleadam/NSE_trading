import os
import sys
import time
import logging
import datetime
import schedule
import threading
import subprocess
from dotenv import load_dotenv
from kiteconnect import KiteConnect

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import modules
from auth.kite_auth import KiteAuth
from core.strategy import Strategy
from core.order_manager import OrderManager
from core.expiry_manager import ExpiryManager
from core.risk_manager import RiskManager
from core.streaming import StreamingService
from utils.logger import Logger
from utils.dashboard import run_dashboard
from utils.notification import NotificationManager
from config import Config

class Application:
    def __init__(self):
        """
        Initialize the application
        """
        # Create logger
        self.logger = Logger().get_logger()
        self.logger.info("Application: Initializing application")
        
        # Load configuration
        self.config = Config()
        self.logger.info("Application: Configuration loaded")
        
        # Authenticate with Kite
        self.kite_auth = KiteAuth(self.logger)
        self.kite = self.kite_auth.authenticate()
        self.logger.info("Application: Authentication completed")
        
        # Initialize components
        self.order_manager = OrderManager(self.kite, self.logger, self.config)
        
        # Download instruments data
        self.order_manager.download_instruments()
        self.expiry_manager = ExpiryManager(self.kite, self.logger, self.config)
        self.risk_manager = RiskManager(self.kite, self.logger, self.config, self.order_manager)
        self.streaming_service = StreamingService(self.kite, self.logger, self.config)
        self.notification_manager = NotificationManager(self.logger, self.config)
        
        # Initialize strategy
        self.strategy = Strategy(
            self.kite,
            self.logger,
            self.config,
            self.order_manager,
            self.expiry_manager,
            self.risk_manager,
            self.streaming_service
        )
        
        self.logger.info("Application: All components initialized")

        # Send startup notification
        self.notification_manager.send_notification("NSE Trading application started", "INFO")

        # Initialize dashboard thread
        self.dashboard_thread = None
        
        # Initialize shutdown flag
        self.shutdown_flag = False
    
    def run(self):
        """
        Run the application
        """
        self.logger.info("Application: Starting application")
        
        # Start streaming service
        self.streaming_service.start()
        
        # Schedule strategy execution
        self._schedule_strategy()
        
        # Start dashboard in a separate thread
        self._start_dashboard()
        
        # Run the scheduler
        self._run_scheduler()
    
    def _schedule_strategy(self):
        """
        Schedule strategy execution
        """
        self.logger.info(f"Application: Scheduling strategy execution every {self.config.run_interval} minutes")
        
        # Schedule strategy execution
        schedule.every(self.config.run_interval).minutes.do(self._execute_strategy)
        
        # Also run once at startup
        self._execute_strategy()
    
    def _execute_strategy(self):
        """
        Execute the strategy
        """
        self.logger.info("Application: Executing strategy")
        
        try:
            # Execute strategy
            result = self.strategy.execute()
            
            if not result:
                self.logger.warning("Application: Strategy execution failed or returned False")
            
            return result
        except Exception as e:
            self.logger.error(f"Application: Error executing strategy: {str(e)}")
            return False
    
    def _run_scheduler(self):
        """
        Run the scheduler
        """
        self.logger.info("Application: Running scheduler")
        
        try:
            while not self.shutdown_flag:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Application: Keyboard interrupt received, shutting down")
            self.shutdown()
        except Exception as e:
            self.logger.error(f"Application: Error in scheduler: {str(e)}")
            self.shutdown()
    
    def _start_dashboard(self):
        """
        Start the Streamlit dashboard in a separate thread
        """
        self.logger.info("Application: Starting dashboard")
        
        # Create a function to run the dashboard
        def run_dashboard_process():
            try:
                # Create dashboard script
                dashboard_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard_app.py")
                
                with open(dashboard_script, "w") as f:
                    f.write("""
import os
import sys
import streamlit as st

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import modules
from auth.kite_auth import KiteAuth
from core.order_manager import OrderManager
from core.expiry_manager import ExpiryManager
from core.risk_manager import RiskManager
from core.strategy import Strategy
from utils.logger import Logger
from utils.dashboard import run_dashboard
from config import Config

# Create logger
logger = Logger().get_logger()

# Load configuration
config = Config()

# Authenticate with Kite
kite_auth = KiteAuth(logger)
kite = kite_auth.authenticate()

# Initialize components
order_manager = OrderManager(kite, logger, config)
expiry_manager = ExpiryManager(kite, logger, config)
risk_manager = RiskManager(kite, logger, config, order_manager)

# Initialize strategy
strategy = Strategy(
    kite,
    logger,
    config,
    order_manager,
    expiry_manager,
    risk_manager,
    None  # No streaming service in dashboard
)

# Run dashboard
run_dashboard(kite, logger, config, order_manager, risk_manager, strategy)
                    """)
                
                # Run the dashboard using streamlit
                subprocess.run(["streamlit", "run", dashboard_script])
            except Exception as e:
                self.logger.error(f"Application: Error starting dashboard: {str(e)}")
        
        # Start the dashboard in a separate thread
        self.dashboard_thread = threading.Thread(target=run_dashboard_process)
        self.dashboard_thread.daemon = True
        self.dashboard_thread.start()
        
        self.logger.info("Application: Dashboard started")
    
    def shutdown(self):
        """
        Shutdown the application
        """
        self.logger.info("Application: Shutting down")
        
        # Set shutdown flag
        self.shutdown_flag = True
        
        # Stop streaming service
        self.streaming_service.stop()
        
        # Wait for dashboard thread to finish
        if self.dashboard_thread and self.dashboard_thread.is_alive():
            self.dashboard_thread.join(timeout=5)

        # Send shutdown notification
        self.notification_manager.send_notification("NSE Trading application shut down", "INFO")

        self.logger.info("Application: Shutdown complete")

if __name__ == "__main__":
    # Create and run application
    app = Application()
    app.run()
