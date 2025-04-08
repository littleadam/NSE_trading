%%writefile /content/core/trade_journal.py
import csv
import os
from datetime import datetime
from config import settings

class TradeJournal:
    def __init__(self):
        self.log_dir = "logs"
        self._init_files()
        
    def _init_files(self):
        """Initialize log files with headers"""
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Trade journal CSV
        if not os.path.exists(f"{self.log_dir}/trades.csv"):
            with open(f"{self.log_dir}/trades.csv", 'w') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'order_id', 'symbol', 'type', 
                    'quantity', 'price', 'status', 'premium',
                    'underlying', 'vix', 'pnl', 'error'
                ])
        
        # Daily summary CSV
        if not os.path.exists(f"{self.log_dir}/daily_summary.csv"):
            with open(f"{self.log_dir}/daily_summary.csv", 'w') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'date', 'start_time', 'end_time', 
                    'total_trades', 'realized_pnl',
                    'unrealized_pnl', 'max_drawdown'
                ])

    def log_trade(self, trade_data):
        """Record individual trade execution"""
        try:
            with open(f"{self.log_dir}/trades.csv", 'a') as f:
                writer = csv.writer(f)
                writer.writerow([
                    datetime.now().isoformat(),
                    trade_data.get('order_id', ''),
                    trade_data.get('symbol', ''),
                    trade_data.get('type', ''),
                    trade_data.get('quantity', 0),
                    trade_data.get('price', 0.0),
                    trade_data.get('status', 'PENDING'),
                    trade_data.get('premium', 0.0),
                    trade_data.get('underlying', 0.0),
                    trade_data.get('vix', 0.0),
                    trade_data.get('pnl', 0.0),
                    trade_data.get('error', '')
                ])
        except Exception as e:
            print(f"Trade logging failed: {str(e)}")

    def log_daily_summary(self):
        """Generate end-of-day report"""
        try:
            with open(f"{self.log_dir}/daily_summary.csv", 'a') as f:
                writer = csv.writer(f)
                writer.writerow([
                    datetime.now().strftime('%Y-%m-%d'),
                    settings.TRADE_CONFIG['trading_hours']['start'],
                    settings.TRADE_CONFIG['trading_hours']['end'],
                    0,  # Placeholder - actual values would be calculated
                    0,  # Realized PNL
                    0,  # Unrealized PNL
                    0   # Max drawdown
                ])
        except Exception as e:
            print(f"Daily summary failed: {str(e)}")

    def log_risk_event(self, event_type, details):
        """Record risk management events"""
        risk_file = f"{self.log_dir}/risk_events.csv"
        try:
            if not os.path.exists(risk_file):
                with open(risk_file, 'w') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        'timestamp', 'event_type', 'details',
                        'ce_positions', 'pe_positions', 'vix'
                    ])
            
            with open(risk_file, 'a') as f:
                writer = csv.writer(f)
                writer.writerow([
                    datetime.now().isoformat(),
                    event_type,
                    str(details),
                    0,  # CE positions count
                    0,  # PE positions count
                    0   # VIX value
                ])
        except Exception as e:
            print(f"Risk event logging failed: {str(e)}")
