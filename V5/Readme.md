# Google Colab Setup and Test Runner for Options Trading Strategy Tests

# 1. Install required packages
!pip install kiteconnect pandas unittest-xml-reporting coverage

# 2. Clone your repository (replace with your actual repo URL)
!git clone https://github.com/littleadam/NSE_trading/tree/main/V5
%cd NSE_trading

# 3. Create mock config.py since it wasn't provided in your files
%%writefile config.py
class Config:
    # Strategy
    STRADDLE_FLAG = True
    STRANGLE_FLAG = False
    BIAS = 0
    STRANGLE_GAP = 1000
    PROFIT_POINTS = 250
    POSITION_STOPLOSS = 50
    
    # Order Management
    ADD_ON_PROFIT = False
    HEDGE_ONE_LOT = True
    LOT_SIZE = 50
    
    # Expiry
    FAR_MONTH_INDEX = 3
    ROLLOVER_DAYS_THRESHOLD = 1
    
    # Risk Management
    SHUTDOWN_LOSS = 12.5
    MARGIN_UTILIZATION_LIMIT = 75
    
    # Additional
    MAX_SPREAD_PCT = 0.05
    ADJACENCY_GAP = 100
    TRADE_DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
    
    # Trading Calendar Mock
    class TRADING_CALENDAR:
        @staticmethod
        def is_trading_day(date):
            # Simple mock - treat all weekdays as trading days
            return date.weekday() < 5

# 4. Create empty .env file to avoid import errors
!touch .env

# 5. Run the tests with coverage and generate XML report
!python -m coverage run --source=core -m unittest tests/test_strategies.py
!python -m coverage report -m
!python -m coverage html

# 6. Display the coverage report
from IPython.display import HTML
HTML(filename='htmlcov/index.html')

# 7. Optional: Download the coverage report
from google.colab import files
!zip -r coverage_report.zip htmlcov/
files.download('coverage_report.zip')
