class Config:
    def __init__(self):
        # Strategy configuration
        self.straddle = True  # If True, implement short straddle; if False, check strangle
        self.strangle = False  # If True, implement short strangle
        self.bias = 0  # Bias to add to spot price for strike selection
        self.strangle_distance = 1000  # Points away from spot price for strangle legs
        # Trend-based strategy configuration
        self.trend = "sideways"  # Options: "bullish", "bearish", "sideways"
        self.trend_distance = 2000  # Points away for trend-based orders
        self.strategy_conversion_threshold = 5  # Percentage increase to convert strategy
        
        # Trading parameters
        self.lot_size = 75  # Number of shares per lot
        self.use_dynamic_lot_size = True  # Whether to use dynamic lot size from instrument data
        self.strike_gap = 50 # points difference between to adjacent strike prices
        self.profit_percentage = 25  # Percentage profit to trigger stop loss and new orders
        self.stop_loss_percentage = 90  # Percentage of original premium to set stop loss
        self.profit_points = 250  # Points of profit to exit all trades on one side (Rs.18750)
        self.shutdown_loss = 12.5  # Percentage of portfolio investment for max loss
        self.adjacency_gap = 200  # Gap for new sell orders when hedge buy orders are in loss
        
        # Hedge configuration
        self.buy_hedge = True  # Whether to place hedge buy orders
        self.hedge_one_lot = True  # If True, buy quantity is one lot; if False, calculate based on sell quantity
        self.far_sell_add = True  # If True, add sell order for same monthly expiry; if False, add next week expiry
        self.far_month_expiry = 3 # Third expiry from the current date is far month expiry
        
        # Schedule configuration
        self.start_time = "09:15:00"
        self.end_time = "15:30:00"
        self.run_interval = 5  # Minutes between each run
        self.trading_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        self.holiday_dates = [
            "2025-01-26",  # Republic Day
            "2025-08-15",  # Independence Day
            "2025-10-02",  # Gandhi Jayanti
            # Add more holiday dates as needed
        ]
        self.special_trading_dates = [
            # Add special Saturday/Sunday trading dates here
            # Format: "YYYY-MM-DD"
        ]
        
        # Portfolio configuration
        self.capital_allocated = 500000  # Capital allocated to this strategy
        
        # Authentication
        self.redirect_url = "https://localhost:8080"
        
        # Logging
        self.log_level = "INFO"
        self.log_file = "nse_trading.log"
        self.error_log_file = "error.log"
       
        # API robustness
        self.max_retries = 3  # Maximum number of retries for API calls
        self.retry_delay = 2  # Seconds to wait between retries
        
        # Notification settings
        self.enable_notifications = True
        self.telegram_bot_token = ""  # Your Telegram bot token
        self.telegram_chat_id = ""    # Your Telegram chat ID
        self.email_sender = ""        # Email sender address
        self.email_password = ""      # Email sender password
        self.email_recipient = ""     # Email recipient address
        self.email_smtp_server = "smtp.gmail.com"
        self.email_smtp_port = 587
        
        # Order tags
        self.tags = {
            "straddle_ce": "short_straddle_ce",
            "straddle_pe": "short_straddle_pe",
            "strangle_ce": "short_strangle_ce",
            "strangle_pe": "short_strangle_pe",
            "hedge_ce": "hedge_buy_ce",
            "hedge_pe": "hedge_buy_pe",
            "trend_ce": "trend_ce",
            "trend_pe": "trend_pe",
            "stop_loss": "stop_loss",
            "additional_sell": "additional_sell",
            "hedge_loss_sell": "hedge_loss_sell",
            "close_position": "close_position",
            "replacement_hedge": "replacement_hedge",
            "far_month_hedge": "far_month_hedge"
        }
