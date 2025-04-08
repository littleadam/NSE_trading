%%writefile config.py
# Configuration variables
API_KEY = "your_api_key"
ACCESS_TOKEN = "your_access_token"
BIAS = 0
ADJACENCY_GAP = 50
PROFIT_POINTS = 250
SHUTDOWN_LOSS = 0.125
STRADDLE_FLAG = True
STRANGLE_FLAG = False
FAR_SELL_ADD = True
BUY_HEDGE = True
CHECK_INTERVAL = 300
TRADING_HOURS = {"start": "09:15", "end": "15:30"}
EXPIRY_MONTHS = 3
STRANGLE_DISTANCE = 1000
PROFIT_THRESHOLD = 0.25
STOPLOSS_THRESHOLD = 0.90
LOGGING_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
HEARTBEAT_INTERVAL = 60  # Seconds
ROLLOVER_BUFFER_MINUTES = 30  # Time before expiry to roll positions
