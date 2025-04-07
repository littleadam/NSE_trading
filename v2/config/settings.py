%%writefile /content/config/settings.py
API_CREDENTIALS = {
    "api_key": "YOUR_API_KEY",
    "access_token": "YOUR_ACCESS_TOKEN"
}

TRADE_CONFIG = {
    # Trading Parameters
    "bias": 50,
    "profit_threshold": 0.25,
    "sl_trigger": 0.9,
    "vix_threshold": 30.0,
    "lot_size": 50,
    "far_sell_add": True,
    "buy_hedge": True,
    "hedge_multiplier": 1.0,
    "max_unrealized_loss_pct": 10,  # New parameter
    
    # Exit Strategy
    "exit_points": {
        "net_gain": 250,
        "rupee_value": 18750
    },
    
    # Schedule Config
    "schedule_interval": 5,
    "trading_hours": {
        "start": "09:15",
        "end": "15:30"
    },
    "weekly_schedule": {
        "days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
        "holidays": [],
        "special_weekends": []
    }
}
