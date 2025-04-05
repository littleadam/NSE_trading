# Ironfly Options Trading Automation System

![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

A sophisticated algorithmic trading system for managing Ironfly options strategies on NSE using Zerodha Kite Connect API.

## Features

### Core Trading Features
- Real-time LTP monitoring through WebSocket
- Automated stop-loss placement and rollover
- VIX-based position liquidation (threshold: 30)
- Monthly expiry rollover management
- Dynamic strike price adjustment

### Risk Management
- Circuit breaker pattern (5 errors/losses)
- Margin utilization monitoring (10% buffer)
- Position concentration limits
- Volatility-based order throttling
- Daily loss limits (5% of net margin)

### Reporting & Analytics
- JSON trade journal with full order details
- Hourly CSV performance snapshots
- Realized/Unrealized P&L tracking
- Breakeven point calculation
- Order lifecycle auditing

## System Architecture

```
Ironfly Automation System
├── Real-time Data Feed
│   ├── WebSocket Tick Processing
│   └── Market Depth Analysis
│
├── Decision Engine
│   ├── Profit/Loss Calculator
│   ├── Expiry Rollover Manager
│   └── Strike Price Optimizer
│
├── Order Execution
│   ├── Smart Order Routing
│   ├── Retry Mechanism
│   └── Transaction Cost Analysis
│
└── Risk Framework
    ├── Margin Monitor
    ├── Exposure Calculator
    └── Circuit Breaker
```

## Code Flow

1. **Initialization**
   - Load configuration from `config/settings.py`
   - Connect to Kite Connect API
   - Initialize positions from broker
   - Start WebSocket connection

2. **Real-Time Processing**
   ```mermaid
   graph TD
   A[WebSocket Connection] --> B[Tick Received]
   B --> C{VIX Check}
   C -->|VIX > 30| D[Close All Positions]
   C -->|VIX Normal| E[Process Strategy Rules]
   E --> F{Profit Threshold Met?}
   F -->|Yes| G[Execute Rollover]
   F -->|No| H{SL Triggered?}
   H -->|Yes| I[Place Hedge Order]
   H -->|No| J[Update Position Tracking]
   ```

3. **Order Lifecycle**
   - Pre-trade checks (Margin, Volatility, Liquidity)
   - Order placement with unique ID
   - Status tracking (Pending/Completed/Rejected)
   - Post-trade reconciliation
   - Hourly snapshot generation

## State Transitions

| Current State       | Event                   | Next State        | Action Taken               |
|---------------------|-------------------------|-------------------|----------------------------|
| IDLE                | WebSocket Connected     | CONNECTED         | Subscribe to instruments   |
| CONNECTED           | Positions Initialized   | MONITORING        | Start tick processing      |
| MONITORING          | Profit Threshold Met    | ORDER_PENDING     | Initiate rollover          |
| ORDER_PENDING       | Order Success           | RISK_CHECK        | Validate exposure          |
| RISK_CHECK          | Validation Passed       | COMPLETED         | Update journal             |
| ANY STATE           | Circuit Breaker Tripped | LOCKED            | Cancel all pending orders  |

## Setup Instructions

### Prerequisites
- Zerodha Demat Account with API access
- Python 3.8+
- Kite Connect API credentials

### Installation
1. Clone repository:
   ```bash
   git clone https://github.com/yourusername/ironfly-automation.git
   cd ironfly-automation
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure settings:
   ```python
   # config/settings.py
   API_CREDENTIALS = {
       "api_key": "your_kite_api_key",
       "access_token": "your_generated_access_token"
   }
   
   TRADE_CONFIG = {
       "max_sells": 2,
       "profit_threshold": 0.25,  # 25%
       "vix_threshold": 30.0
   }
   ```

4. Run the application:
   ```bash
   python main.py
   ```

## Security Considerations
- **Credential Management**
  - Never commit API keys to version control
  - Use environment variables for production
  - Rotate access tokens weekly
  
- **Network Security**
  - Enable 2FA on Zerodha account
  - Restrict API access to whitelisted IPs
  - Use VPN for remote access
  
- **Data Protection**
  - Encrypt log files containing trade data
  - Regularly audit snapshot files
  - Implement filesystem permissions (600)

## Logging & Reporting

### Trade Journal (`trading_journal.log`)
```json
{
  "timestamp": "2023-07-20T14:23:01.456Z",
  "order_id": "2307201423N123456",
  "tradingsymbol": "NIFTY25JUN20500CE",
  "transaction_type": "SELL",
  "quantity": 75,
  "premium": 123.45,
  "option_type": "CE",
  "status": "COMPLETED",
  "market_conditions": {
    "nifty_spot": 19875.4,
    "india_vix": 12.34
  }
}
```

### Performance Snapshot (`trading_snapshot.csv`)

| timestamp          | active_orders | realized_pnl | monthly_be |
|---------------------|---------------|--------------|------------|
| 2023-07-20T15:00:00 | 2             | 4567.89      | 19850      |
| 2023-07-20T16:00:00 | 1             | 5123.45      | 19855      |

**Snapshot Metrics:**
- **Realized P&L:** Sum of closed position profits
- **Monthly Breakeven:** Weighted average of active positions
- **Exposure Ratio:** (Total Risk / Net Margin) * 100

## License

MIT License - See [LICENSE](LICENSE) for full text.

---

**Disclaimer:** This software is for educational purposes only. Use at your own risk. Past performance is not indicative of future results. The developers assume no liability for any trading losses incurred.
