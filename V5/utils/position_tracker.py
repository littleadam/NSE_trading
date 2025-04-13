# utils/position_tracker.py
import logging
from datetime import datetime
from typing import Dict, List, Optional

from kiteconnect import KiteConnect
from config import Config
from utils.helpers import retry_api_call
from utils.logger import logger

logger = logging.getLogger(__name__)

class PositionTracker:
    """Unified position tracking and conflict detection class"""
    
    def __init__(self, kite: KiteConnect):
        self.kite = kite
        self.positions: List[Dict] = []
        self.last_updated: Optional[datetime] = None

    @retry_api_call(max_retries=3, backoff=1)
    def update_positions(self) -> None:
        """Refresh positions from broker API with P&L calculation"""
        try:
            # Prevent excessive API calls
            if self.last_updated and (datetime.now() - self.last_updated).seconds < 10:
                logger.debug("Skipping position update - recent data available")
                return

            raw_positions = self.kite.positions()['net']
            holdings = self.kite.holdings()
            self.positions = []

            for pos in raw_positions:
                if pos['product'] == 'MIS' and pos['quantity'] != 0:
                    ltp = self._get_ltp(pos['tradingsymbol'])
                    unrealized_pnl = (ltp - pos['average_price']) * pos['quantity'] * Config.LOT_SIZE
                    
                    self.positions.append({
                        'symbol': pos['tradingsymbol'],
                        'quantity': pos['quantity'],
                        'entry_price': pos['average_price'],
                        'ltp': ltp,
                        'unrealized_pnl': unrealized_pnl,
                        'expiry': datetime.strptime(pos['expiry'], '%Y-%m-%d').date(),
                        'strike': pos['strike'],
                        'instrument_type': pos['instrument_type']
                    })
            
            self.last_updated = datetime.now()
            logger.debug(f"Updated {len(self.positions)} positions")

        except Exception as e:
            logger.error(f"Position update failed: {str(e)}")
            raise

    def get_conflicts(self, strategy_type: str, expiry: datetime.date) -> List[Dict]:
        """Identify conflicting positions for given strategy/expiry"""
        conflicts = []
        for pos in self.positions:
            if pos['expiry'] != expiry:
                continue
                
            if strategy_type == 'STRADDLE' and \
                abs(pos['strike'] - pos['entry_price']) <= Config.ADJACENCY_GAP:
                conflicts.append(pos)
            
            elif strategy_type == 'STRANGLE' and \
                (pos['strike'] >= (pos['entry_price'] + Config.STRANGLE_GAP) or 
                 pos['strike'] <= (pos['entry_price'] - Config.STRANGLE_GAP)):
                conflicts.append(pos)
        
        return conflicts

    def get_positions(self) -> List[Dict]:
        """Get current positions with P&L data"""
        return self.positions

    def _get_ltp(self, symbol: str) -> float:
        """Get last traded price for a symbol"""
        try:
            return self.kite.ltp(f"NFO:{symbol}")[f"NFO:{symbol}"]['last_price']
        except Exception as e:
            logger.error(f"LTP fetch failed for {symbol}: {str(e)}")
            return 0.0

    def has_active_positions(self) -> bool:
        """Check if any active positions exist"""
        return len(self.positions) > 0

    def get_position(self, symbol: str) -> Optional[Dict]:
        """Get specific position by tradingsymbol"""
        return next((p for p in self.positions if p['symbol'] == symbol), None)

    def clear_positions(self) -> None:
        """Reset position cache"""
        self.positions = []
        self.last_updated = None
