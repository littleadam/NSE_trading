import csv
import os
from datetime import datetime

class TradeJournal:
    def __init__(self, kite_client):
        print("Initializing Trade Journal...")
        self.kite = kite_client
        self.log_dir = "logs"
        self.journal_file = os.path.join(self.log_dir, "trades.csv")
        self.snapshot_file = os.path.join(self.log_dir, "snapshots.csv")
        self._ensure_directory()
        self._initialize_files()

    def _ensure_directory(self):
        try:
            os.makedirs(self.log_dir, exist_ok=True)
            print(f"Created log directory: {self.log_dir}")
        except Exception as e:
            print(f"Directory creation error: {str(e)}")
            raise

    def _initialize_files(self):
        try:
            if not os.path.exists(self.journal_file):
                with open(self.journal_file, 'w') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        'timestamp', 'order_id', 'symbol', 'type',
                        'quantity', 'price', 'status', 'premium',
                        'underlying', 'vix', 'error'
                    ])
                print("Created new trade journal file")
                
            if not os.path.exists(self.snapshot_file):
                with open(self.snapshot_file, 'w') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        'timestamp', 'active', 'closed',
                        'realized_pnl', 'unrealized_pnl', 'breakeven'
                    ])
                print("Created new snapshot file")
                
        except Exception as e:
            print(f"File initialization error: {str(e)}")
            raise

    def record_order(self, order_data):
        print(f"Recording order {order_data.get('order_id', '')}")
        try:
            underlying = self._get_underlying_price()
            vix = self._get_vix()
            
            with open(self.journal_file, 'a') as f:
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
                    underlying,
                    vix,
                    order_data.get('error', '')
                ])
            print("Order recorded successfully")
            
        except Exception as e:
            print(f"Order recording failed: {str(e)}")

    def generate_snapshot(self):
        print("Generating performance snapshot...")
        try:
            snapshot = {
                'timestamp': datetime.now().isoformat(),
                'active': self._count_active_orders(),
                'closed': self._count_closed_orders(),
                'realized_pnl': self._calculate_realized_pnl(),
                'unrealized_pnl': self._calculate_unrealized_pnl(),
                'breakeven': self._calculate_breakeven()
            }
            
            with open(self.snapshot_file, 'a') as f:
                writer = csv.writer(f)
                writer.writerow(snapshot.values())
                
            print(f"Snapshot generated: {snapshot}")
            return snapshot
            
        except Exception as e:
            print(f"Snapshot generation failed: {str(e)}")
            return None

    def _count_active_orders(self):
        try:
            with open(self.journal_file, 'r') as f:
                return sum(1 for row in csv.DictReader(f) 
                          if row['status'] in ['PENDING', 'TRIGGER_PENDING'])
        except Exception as e:
            print(f"Active order count error: {str(e)}")
            return 0

    def _calculate_realized_pnl(self):
        try:
            total = 0.0
            with open(self.journal_file, 'r') as f:
                for row in csv.DictReader(f):
                    if row['status'] == 'COMPLETE':
                        multiplier = -1 if row['type'] == 'BUY' else 1
                        total += float(row['premium']) * int(row['quantity']) * multiplier
            return round(total, 2)
        except Exception as e:
            print(f"P&L calculation error: {str(e)}")
            return 0.0
