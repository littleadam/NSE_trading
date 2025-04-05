import csv
import os
from datetime import datetime
from kiteconnect import KiteConnect
import logging

class TradeJournal:
    def __init__(self, kite_client):
        self.kite = kite_client
        self.log_dir = "logs"
        self.journal_file = os.path.join(self.log_dir, "trading_journal.csv")
        self.snapshot_file = os.path.join(self.log_dir, "performance_snapshot.csv")
        
        print("Initializing Trade Journal...")
        self._ensure_log_directory()
        self._initialize_files()
        print(f"Trade Journal ready. Files stored in: {os.path.abspath(self.log_dir)}")

    def _ensure_log_directory(self):
        """Create log directory if not exists"""
        try:
            os.makedirs(self.log_dir, exist_ok=True)
            print(f"Created log directory: {self.log_dir}")
        except Exception as e:
            print(f"Failed to create log directory: {str(e)}")
            raise

    def _initialize_files(self):
        """Initialize CSV files with headers if they don't exist"""
        try:
            if not os.path.exists(self.journal_file):
                print("Creating new trade journal file...")
                with open(self.journal_file, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        'timestamp', 'order_id', 'symbol', 'transaction_type',
                        'quantity', 'price', 'status', 'premium',
                        'underlying_price', 'vix_value', 'error_message'
                    ])
                print("Trade journal file initialized")

            if not os.path.exists(self.snapshot_file):
                print("Creating new performance snapshot file...")
                with open(self.snapshot_file, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        'timestamp', 'active_orders', 'closed_orders',
                        'realized_pnl', 'unrealized_pnl', 'breakeven_point'
                    ])
                print("Performance snapshot file initialized")
        except Exception as e:
            print(f"File initialization failed: {str(e)}")
            raise

    def record_order(self, order_data):
        """Record order details to the journal"""
        print(f"Recording order {order_data.get('order_id', 'N/A')}...")
        try:
            underlying_price = self._get_underlying_price()
            vix_value = self._get_vix_value()
            
            with open(self.journal_file, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    datetime.now().isoformat(),
                    order_data.get('order_id', ''),
                    order_data.get('tradingsymbol', ''),
                    order_data.get('transaction_type', ''),
                    order_data.get('quantity', 0),
                    order_data.get('price', 0.0),
                    order_data.get('status', 'PENDING'),
                    order_data.get('average_price', 0.0),
                    underlying_price,
                    vix_value,
                    order_data.get('error_message', '')
                ])
            print(f"Order {order_data.get('order_id', 'N/A')} recorded successfully")
        except Exception as e:
            print(f"Failed to record order: {str(e)}")
            logging.error(f"Order recording error: {str(e)}")

    def generate_snapshot(self):
        """Generate performance snapshot"""
        print("Generating performance snapshot...")
        try:
            snapshot_data = {
                'timestamp': datetime.now().isoformat(),
                'active_orders': self._get_active_order_count(),
                'closed_orders': self._get_closed_order_count(),
                'realized_pnl': self._calculate_realized_pnl(),
                'unrealized_pnl': self._calculate_unrealized_pnl(),
                'breakeven_point': self._calculate_breakeven()
            }
            
            with open(self.snapshot_file, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    snapshot_data['timestamp'],
                    snapshot_data['active_orders'],
                    snapshot_data['closed_orders'],
                    snapshot_data['realized_pnl'],
                    snapshot_data['unrealized_pnl'],
                    snapshot_data['breakeven_point']
                ])
            print("Snapshot generated successfully")
            return snapshot_data
        except Exception as e:
            print(f"Failed to generate snapshot: {str(e)}")
            logging.error(f"Snapshot error: {str(e)}")
            return None

    def _get_active_order_count(self):
        """Count active orders from journal"""
        try:
            with open(self.journal_file, 'r') as f:
                reader = csv.DictReader(f)
                return sum(1 for row in reader if row['status'] in ['PENDING', 'TRIGGER_PENDING'])
        except Exception as e:
            print(f"Error counting active orders: {str(e)}")
            return 0

    def _get_closed_order_count(self):
        """Count closed orders from journal"""
        try:
            with open(self.journal_file, 'r') as f:
                reader = csv.DictReader(f)
                return sum(1 for row in reader if row['status'] in ['COMPLETE', 'REJECTED'])
        except Exception as e:
            print(f"Error counting closed orders: {str(e)}")
            return 0

    def _calculate_realized_pnl(self):
        """Calculate realized P&L from closed orders"""
        try:
            with open(self.journal_file, 'r') as f:
                reader = csv.DictReader(f)
                return sum(
                    float(row['premium']) * (-1 if row['transaction_type'] == 'BUY' else 1)
                    for row in reader if row['status'] == 'COMPLETE'
                )
        except Exception as e:
            print(f"Error calculating realized P&L: {str(e)}")
            return 0.0

    def _calculate_unrealized_pnl(self):
        """Calculate unrealized P&L from open positions"""
        try:
            positions = self.kite.positions()['net']
            return sum(
                (position['last_price'] - position['average_price']) * position['quantity']
                for position in positions if position['product'] == 'OPT'
            )
        except Exception as e:
            print(f"Error calculating unrealized P&L: {str(e)}")
            return 0.0

    def _calculate_breakeven(self):
        """Calculate breakeven point for current positions"""
        try:
            positions = self.kite.positions()['net']
            if not positions:
                return 0.0
            total_premium = sum(p['average_price'] * p['quantity'] for p in positions)
            total_quantity = sum(abs(p['quantity']) for p in positions)
            return total_premium / total_quantity if total_quantity != 0 else 0.0
        except Exception as e:
            print(f"Error calculating breakeven: {str(e)}")
            return 0.0

    def _get_underlying_price(self):
        """Get current underlying price"""
        try:
            return self.kite.ltp(f"NSE:{TRADE_CONFIG['underlying']}")[f"NSE:{TRADE_CONFIG['underlying']}"]['last_price']
        except Exception as e:
            print(f"Error fetching underlying price: {str(e)}")
            return 0.0

    def _get_vix_value(self):
        """Get current India VIX value"""
        try:
            return self.kite.ltp(f"NSE:{TRADE_CONFIG['vix_symbol']}")[f"NSE:{TRADE_CONFIG['vix_symbol']}"]['last_price']
        except Exception as e:
            print(f"Error fetching VIX value: {str(e)}")
            return 0.0
