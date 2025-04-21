# NSE Trading Application - Short Straddle/Strangle Strategy

This application implements automated trading for short straddle and short strangle options strategies on Nifty using the Zerodha Kite API. The application focuses on maintaining positions in far month expiry options with specific rules for profit taking, hedging, and risk management.

## Features

- Implements both short straddle and short strangle strategies
- Targets far month expiry (3 monthly expiries away)
- Automatically sets stop loss at 90% when a leg reaches 25% profit
- Adds new sell orders at the same strike price when profit targets are reached
- Implements hedge buy orders in upcoming weekly expiry
- Manages expiry day operations by replacing expiring hedge positions
- Implements profit exit conditions (250 points) and shutdown loss conditions (12.5%)
- Handles orphan hedge orders and spot price touching hedge strike scenarios
- Runs on a configurable schedule during market hours

## Project Structure

```
NSE_trading/  
├── main.py                 # Entry point  
├── config.py               # All parameters  
├── auth/  
│   ├── kite_auth.py        # OAuth2 flow  
│   └── .env                # API credentials  
├── core/  
│   ├── strategy.py         # Straddle/Strangle logic  
│   ├── risk_manager.py     # Shutdown triggers    
│   ├── order_manager.py    # Order placement  
│   ├── expiry_manager.py   # Expiry handling  
│   └── streaming.py        # Real-time data  
├── utils/  
│   ├── helpers.py          # Common utilities  
│   ├── logger.py           # Structured logging  
│   └── position_analyzer.py # Position analysis  
└── tests/                  # Unit tests
    ├── test_strategies.py  # Strategy tests
    └── test_core_modules.py # Core module tests
```

## Configuration

All strategy parameters are configurable in `config.py`:

- `straddle`: Enable short straddle strategy
- `strangle`: Enable short strangle strategy
- `bias`: Bias to add to spot price for strike selection
- `strangle_distance`: Points away from spot price for strangle legs (approximately 1000 points)
- `lot_size`: Number of shares per lot
- `profit_percentage`: Percentage profit to trigger stop loss and new orders (25%)
- `stop_loss_percentage`: Percentage of original premium to set stop loss (90%)
- `profit_points`: Points of profit to exit all trades on one side (250 points)
- `shutdown_loss`: Percentage of portfolio investment for max loss (12.5%)
- `adjacency_gap`: Gap for new sell orders when hedge buy orders are in loss (200 points)
- `buy_hedge`: Whether to place hedge buy orders
- `hedge_one_lot`: If True, buy quantity is one lot; if False, calculate based on sell quantity
- `far_sell_add`: If True, add sell order for same monthly expiry; if False, add next week expiry
- Trading schedule and holiday dates

## Setup and Installation

1. Clone the repository
2. Install required packages
3. Update API credentials in `.env` file
4. Run the setup script to generate access token
5. Run tests to verify functionality
6. Run the main application

See `setup.py` for detailed setup instructions.

## Usage

```python
# Run setup to install dependencies and authenticate
python setup.py

# Run the main application
python main.py
```

## Strategy Logic

### Short Straddle
- Sell CE and PE options at the same strike price (ATM + bias)
- Place hedge buy orders at strike prices calculated as:
  - CE: sell_strike + premium
  - PE: sell_strike - premium

### Short Strangle
- Sell CE and PE options at strike prices approximately 1000 points away from spot price
- Place hedge buy orders at strike prices calculated as:
  - CE: sell_strike + premium
  - PE: sell_strike - premium

### Profit Management
- When a sell leg reaches 25% profit:
  - Set stop loss at 90% of original premium
  - Add a new sell order at the same strike price
  - Add corresponding hedge buy order

### Hedge Management
- When a hedge buy order reaches 25% loss:
  - Add a new sell order at strike price adjusted by adjacency gap
- When spot price touches hedge strike:
  - Close the hedge
  - Add far month buy order at half premium with 2x quantity

### Risk Management
- Exit all trades on one side when profit reaches 250 points
- Exit all trades when unrealized loss exceeds 12.5% of portfolio

## Testing

Run the test suite to verify functionality:

```python
pytest -xvs NSE_trading/tests/
```

## Google Colab Setup

See the Google Colab setup instructions in the next section.

## Disclaimer

This application is for educational purposes only. Trading in derivatives involves substantial risk of loss and is not suitable for all investors. Past performance is not indicative of future results.
