import logging
import os
import datetime

class Logger:
    def __init__(self, config):
        """
        Initialize logger with configuration
        
        Args:
            config: Configuration instance
        """
        self.config = config
        
        # Create logs directory if it doesn't exist
        os.makedirs(os.path.dirname(os.path.abspath(__file__)) + '/../logs', exist_ok=True)
        
        # Set up logger
        self.logger = logging.getLogger('nse_trading')
        self.logger.setLevel(getattr(logging, self.config.log_level))
        
        # Clear existing handlers
        if self.logger.handlers:
            self.logger.handlers.clear()
        
        # Create file handler
        log_file = os.path.dirname(os.path.abspath(__file__)) + '/../logs/' + self.config.log_file
        file_handler = logging.FileHandler(log_file)
        
        # Create console handler
        console_handler = logging.StreamHandler()
        
        # Create formatter
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # Add handlers to logger
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
        self.logger.info(f"Logger: Initialized with log level {self.config.log_level}")
    
    def get_logger(self):
        """
        Get the logger instance
        
        Returns:
            Logger instance
        """
        return self.logger
    
    def log_trade(self, order_id, instrument, transaction_type, quantity, price, status):
        """
        Log a trade with detailed information
        
        Args:
            order_id: Order ID
            instrument: Instrument details
            transaction_type: BUY or SELL
            quantity: Order quantity
            price: Order price
            status: Order status
        """
        self.logger.info(f"TRADE: {order_id} | {instrument} | {transaction_type} | {quantity} | {price} | {status}")
    
    def log_strategy_decision(self, decision, reason):
        """
        Log a strategy decision
        
        Args:
            decision: Decision made
            reason: Reason for the decision
        """
        self.logger.info(f"STRATEGY: {decision} | {reason}")
    
    def log_position_update(self, position):
        """
        Log a position update
        
        Args:
            position: Position details
        """
        self.logger.info(f"POSITION: {position['tradingsymbol']} | Qty: {position['quantity']} | P&L: {position['pnl']}")
    
    def log_error(self, module, error):
        """
        Log an error
        
        Args:
            module: Module where error occurred
            error: Error details
        """
        self.logger.error(f"ERROR: {module} | {error}")
    
    def log_warning(self, module, warning):
        """
        Log a warning
        
        Args:
            module: Module where warning occurred
            warning: Warning details
        """
        self.logger.warning(f"WARNING: {module} | {warning}")
    
    def log_info(self, module, info):
        """
        Log information
        
        Args:
            module: Module providing information
            info: Information details
        """
        self.logger.info(f"INFO: {module} | {info}")
    
    def log_debug(self, module, debug):
        """
        Log debug information
        
        Args:
            module: Module providing debug information
            debug: Debug details
        """
        self.logger.debug(f"DEBUG: {module} | {debug}")
    
    def log_execution_start(self):
        """
        Log the start of strategy execution
        """
        self.logger.info("=" * 80)
        self.logger.info(f"EXECUTION START: {datetime.datetime.now()}")
        self.logger.info("=" * 80)
    
    def log_execution_end(self):
        """
        Log the end of strategy execution
        """
        self.logger.info("=" * 80)
        self.logger.info(f"EXECUTION END: {datetime.datetime.now()}")
        self.logger.info("=" * 80)
