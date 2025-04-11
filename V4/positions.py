%%writefile positions.py
from kiteconnect import KiteConnect
from config import config
from logger import setup_logger
from typing import List, Dict

log = setup_logger()

class PositionManager:
    def __init__(self):
        self.kite = KiteConnect(api_key=config.API_KEY)
        self.kite.set_access_token(config.API_SECRET)
        self.positions = {'net': []}
        self.orders = []

    def sync_positions(self):
        """Synchronize positions from broker"""
        log.info("Syncing positions")
        try:
            self.positions = self.kite.positions()
            self.orders = self.kite.orders()
            log.info(f"Synced {len(self.positions['net'])} net positions")
        except Exception as e:
            log.error("Position sync failed", exc_info=True)
            raise

    def get_active_positions(self, strategy_type: str) -> List[Dict]:
        """Get active positions by strategy"""
        log.info(f"Getting active positions for {strategy_type}")
        return [
            p for p in self.positions.get('net', [])
            if p['product'] == 'MIS' and strategy_type in p.get('tag', '')
        ]

    def calculate_unrealized_pnl(self) -> float:
        """Calculate total unrealized P&L"""
        log.info("Calculating unrealized P&L")
        total = sum(p['unrealised'] for p in self.positions.get('net', []))
        log.info(f"Total unrealized P&L: {total}")
        return total

    def existing_position_check(self, expiry_date: datetime.date, 
                               strike: float, option_type: str) -> bool:
        """Check for existing position"""
        log.debug(f"Checking existing position: {expiry_date}, {strike}, {option_type}")
        target_strike = round_strike(strike)
        for p in self.positions.get('net', []):
            if (p['expiry'] == expiry_date and
                p['strike'] == target_strike and
                p['instrument_type'] == option_type):
                log.debug("Position exists")
                return True
        log.debug("No existing position")
        return False
