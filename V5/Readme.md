#!/bin/bash
# setup_and_test.sh
# Usage: ./setup_and_test.sh

set -e  # Exit immediately if any command fails

# Clone repository (replace with your actual repo URL)
git clone https://github.com/littleadam/NSE_trading/new/main/V5
cd NSE_trading/new/main/V5

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install system dependencies (if needed)
sudo apt-get update && sudo apt-get install -y python3-dev  # For Linux

# Install project dependencies
cat > requirements.txt <<EOL
pytest==7.4.0
pytest-cov==4.1.0
pytest-mock==3.11.1
pandas==2.0.3
python-dotenv==1.0.0
kiteconnect==3.9.3
python-dateutil==2.8.2
requests==2.31.0
EOL

pip install -r requirements.txt

# Set up test directory structure
mkdir -p tests
touch tests/__init__.py

# Create minimal config.py if missing
if [ ! -f config.py ]; then
    cat > config.py <<EOL
class Config:
    STRADDLE_FLAG = True
    STRANGLE_FLAG = False
    BIAS = 0
    STRANGLE_GAP = 1000
    PROFIT_POINTS = 250
    POSITION_STOPLOSS = 50
    ADD_ON_PROFIT = False
    HEDGE_ONE_LOT = True
    LOT_SIZE = 75
    FAR_MONTH_INDEX = 3
    ROLLOVER_DAYS_THRESHOLD = 1
    SHUTDOWN_LOSS = 12.5
    MARGIN_UTILIZATION_LIMIT = 75
    MAX_SPREAD_PCT = 0.05
    ADJACENCY_GAP = 100
    TRADE_DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
    TRADING_CALENDAR = MagicMock()  # Mock for testing
EOL
fi

# Run tests with coverage
python -m pytest tests/test_strategies.py -v \
  --cov=core.strategy \
  --cov-report=term-missing \
  --cov-fail-under=90

# Deactivate virtual environment
deactivate
