import logging
import os
import datetime
import sys
import inspect
from functools import wraps

class Logger:
    def __init__(self, log_level=None, log_file=None, error_log_file=None):
        """
        Initialize Logger with log level and log file
        
        Args:
            log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            log_file: Log file path
            error_log_file: Error log file path
        """
        # Create logs directory if it doesn't exist
        os.makedirs('logs', exist_ok=True)
        
        # Set default log level and log file
        self.log_level = log_level or "INFO"
        self.log_file = log_file or "logs/nse_trading.log"
        self.error_log_file = error_log_file or "logs/error.log"
        
        # Configure logger
        self.logger = logging.getLogger('nse_trading')
        self.logger.setLevel(getattr(logging, self.log_level))
        
        # Clear existing handlers
        self.logger.handlers = []
        
        # Create formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        # Create file handler
        file_handler = logging.FileHandler(self.log_file)
        file_handler.setLevel(getattr(logging, self.log_level))
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        
        # Create error file handler
        error_file_handler = logging.FileHandler(self.error_log_file)
        error_file_handler.setLevel(logging.ERROR)
        error_file_handler.setFormatter(formatter)
        self.logger.addHandler(error_file_handler)
        
        # Create console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, self.log_level))
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
    
    def get_logger(self):
        """
        Get logger instance
        
        Returns:
            Logger instance
        """
        return self.logger
    
    def log_function_call(self, func):
        """
        Decorator to log function calls with arguments and return values
        
        Args:
            func: Function to decorate
            
        Returns:
            Decorated function
        """
        @wraps(func)
        def wrapper(*args, **kwargs):
            func_name = func.__name__
            module_name = func.__module__
            
            # Get calling function and line number
            caller_frame = inspect.currentframe().f_back
            caller_info = ""
            if caller_frame:
                caller_info = f" (called from {caller_frame.f_code.co_name}:{caller_frame.f_lineno})"
            
            # Log function call with arguments
            args_str = ', '.join([repr(arg) for arg in args[1:]])  # Skip self
            kwargs_str = ', '.join([f"{k}={repr(v)}" for k, v in kwargs.items()])
            params = []
            if args_str:
                params.append(args_str)
            if kwargs_str:
                params.append(kwargs_str)
            params_str = ', '.join(params)
            
            self.logger.info(f"{module_name}.{func_name}({params_str}) called{caller_info}")
            
            try:
                # Call the function
                result = func(*args, **kwargs)
                
                # Log return value
                self.logger.info(f"{module_name}.{func_name} returned: {repr(result)}")
                
                return result
            except Exception as e:
                # Log exception
                self.logger.error(f"{module_name}.{func_name} raised: {repr(e)}")
                raise
        
        return wrapper
    
    def log_method(self, level=logging.INFO):
        """
        Decorator to log method calls with arguments and return values at specified level
        
        Args:
            level: Logging level
            
        Returns:
            Decorator function
        """
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                func_name = func.__name__
                class_name = args[0].__class__.__name__ if args else ""
                
                # Get calling function and line number
                caller_frame = inspect.currentframe().f_back
                caller_info = ""
                if caller_frame:
                    caller_info = f" (called from {caller_frame.f_code.co_name}:{caller_frame.f_lineno})"
                
                # Log function call with arguments
                args_str = ', '.join([repr(arg) for arg in args[1:]])  # Skip self
                kwargs_str = ', '.join([f"{k}={repr(v)}" for k, v in kwargs.items()])
                params = []
                if args_str:
                    params.append(args_str)
                if kwargs_str:
                    params.append(kwargs_str)
                params_str = ', '.join(params)
                
                self.logger.log(level, f"{class_name}.{func_name}({params_str}) called{caller_info}")
                
                try:
                    # Call the function
                    result = func(*args, **kwargs)
                    
                    # Log return value
                    self.logger.log(level, f"{class_name}.{func_name} returned: {repr(result)}")
                    
                    return result
                except Exception as e:
                    # Log exception
                    self.logger.error(f"{class_name}.{func_name} raised: {repr(e)}")
                    raise
            
            return wrapper
        
        return decorator
    
    def rotate_logs(self, max_size_mb=10, backup_count=5):
        """
        Rotate log files when they reach a certain size
        
        Args:
            max_size_mb: Maximum size of log file in MB
            backup_count: Number of backup files to keep
        """
        # Check main log file size
        if os.path.exists(self.log_file) and os.path.getsize(self.log_file) > max_size_mb * 1024 * 1024:
            self._rotate_log_file(self.log_file, backup_count)
        
        # Check error log file size
        if os.path.exists(self.error_log_file) and os.path.getsize(self.error_log_file) > max_size_mb * 1024 * 1024:
            self._rotate_log_file(self.error_log_file, backup_count)
    
    def _rotate_log_file(self, log_file, backup_count):
        """
        Rotate a specific log file
        
        Args:
            log_file: Log file path
            backup_count: Number of backup files to keep
        """
        # Remove oldest backup if it exists
        oldest_backup = f"{log_file}.{backup_count}"
        if os.path.exists(oldest_backup):
            os.remove(oldest_backup)
        
        # Shift existing backups
        for i in range(backup_count - 1, 0, -1):
            backup = f"{log_file}.{i}"
            new_backup = f"{log_file}.{i + 1}"
            if os.path.exists(backup):
                os.rename(backup, new_backup)
        
        # Rename current log file to .1
        if os.path.exists(log_file):
            os.rename(log_file, f"{log_file}.1")
        
        # Create new log file
        open(log_file, 'w').close()
        
        # Reconfigure handlers
        self.__init__(self.log_level, self.log_file, self.error_log_file)
    
    def archive_old_logs(self, days=30):
        """
        Archive log files older than specified days
        
        Args:
            days: Number of days to keep logs
        """
        # Create archive directory if it doesn't exist
        archive_dir = os.path.join('logs', 'archive')
        os.makedirs(archive_dir, exist_ok=True)
        
        # Get current time
        now = datetime.datetime.now()
        
        # Check all files in logs directory
        for filename in os.listdir('logs'):
            if filename.startswith('.') or filename == 'archive':
                continue
                
            file_path = os.path.join('logs', filename)
            
            # Check if file is older than specified days
            file_time = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
            if (now - file_time).days > days:
                # Archive file
                archive_path = os.path.join(archive_dir, f"{filename}.{file_time.strftime('%Y%m%d')}")
                os.rename(file_path, archive_path)
                self.logger.info(f"Archived log file: {filename} to {archive_path}")

# Function to get a logger instance with default configuration
def get_default_logger():
    """
    Get a logger instance with default configuration
    
    Returns:
        Logger instance
    """
    return Logger().get_logger()
