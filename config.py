class Config:
    def __init__(self):
        # Strategy configuration
        self.straddle = True  # If True, implement short straddle; if False, check strangle
        self.strangle = False  # If True, implement short strangle
        self.bias = 0  # Bias to add to spot price for strike selection
        self.strangle_distance = 1000  # Points away from spot price for strangle legs
        
        # Trading parameters
        self.lot_size = 75  # Number of shares per lot
        self.profit_percentage = 25  # Percentage profit to trigger stop loss and new orders
        self.stop_loss_percentage = 90  # Percentage of original premium to set stop loss
        self.profit_points = 250  # Points of profit to exit all trades on one side (Rs.18750)
        self.shutdown_loss = 12.5  # Percentage of portfolio investment for max loss
        self.adjacency_gap = 200  # Gap for new sell orders when hedge buy orders are in loss
        
        # Hedge configuration
        self.buy_hedge = True  # Whether to place hedge buy orders
        self.hedge_one_lot = True  # If True, buy quantity is one lot; if False, calculate based on sell quantity
        self.far_sell_add = True  # If True, add sell order for same monthly expiry; if False, add next week expiry
        
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
