# utils/position_tracker.py
import logging
from datetime import datetime
from typing import Dict, List, Optional, Union, Any

from kiteconnect import KiteConnect
from config import Config
from utils.helpers import retry_api_call
from utils.logger import logger

logger = logging.getLogger(__name__)

PositionType = Dict[str, Union[str, float, datetime.date, int]]

class PositionTracker:
    """Enhanced position tracking with directional awareness and conflict detection.
    
    Attributes:
        kite (KiteConnect): Authenticated KiteConnect instance
        positions (List[PositionType]): List of current positions with metadata
        last_updated (Optional[datetime]): Timestamp of last position update
    """

    def __init__(self, kite: KiteConnect) -> None:
        """Initialize PositionTracker with Kite connection.
        
        Args:
            kite: Authenticated KiteConnect instance
        """
        self.kite = kite
        self.positions: List[PositionType] = []
        self.last_updated: Optional[datetime] = None

    @retry_api_call(max_retries=3, backoff=1)
    def update_positions(self) -> None:
        """Refresh positions with directional tracking and accurate P&L calculation."""
        try:
            if self.last_updated and (datetime.now() - self.last_updated).seconds < 10:
                logger.debug("Skipping position update - recent data available")
                return

            raw_positions = self.kite.positions()['net']
            self.positions = []

            for pos in raw_positions:
                if pos['product'] == 'MIS' and pos['quantity'] != 0:
                    quantity = pos['quantity']
                    direction = 'BUY' if quantity > 0 else 'SELL'
                    ltp = self._get_ltp(pos['tradingsymbol'])
                    
                    # Calculate P&L based on direction
                    unrealized_pnl = (
                        (ltp - pos['average_price']) * 
                        abs(quantity) *  # Use absolute quantity
                        Config.LOT_SIZE *
                        (1 if direction == 'SELL' else -1)  # Reverse for long positions
                    )

                    self.positions.append({
                        'symbol': pos['tradingsymbol'],
                        'quantity': quantity,
                        'absolute_quantity': abs(quantity),
                        'entry_price': pos['average_price'],
                        'ltp': ltp,
                        'unrealized_pnl': unrealized_pnl,
                        'expiry': datetime.strptime(pos['expiry'], '%Y-%m-%d').date(),
                        'strike': pos['strike'],
                        'instrument_type': pos['instrument_type'],
                        'direction': direction
                    })

            self.last_updated = datetime.now()
            logger.debug(f"Updated {len(self.positions)} positions with direction data")

        except Exception as e:
            logger.error(f"Position update failed: {str(e)}")
            raise

    def get_conflicts(
        self,
        strategy_type: str,
        expiry: datetime.date,
        transaction_type: str,
        strike: float
    ) -> List[PositionType]:
        """Direction-aware conflict detection with strike proximity check.
        
        Args:
            strategy_type: Trading strategy (STRADDLE/STRANGLE)
            expiry: Options expiry date
            transaction_type: BUY/SELL direction
            strike: Strike price to check
            
        Returns:
            List of conflicting positions
        """
        conflicts = []
        for pos in self.positions:
            if (pos['expiry'] == expiry and
                pos['direction'] == transaction_type and
                abs(pos['strike'] - strike) <= Config.ADJACENCY_GAP):
                
                if strategy_type == 'STRADDLE':
                    conflicts.append(pos)
                elif strategy_type == 'STRANGLE':
                    if (pos['strike'] >= (strike + Config.STRANGLE_GAP) or
                        pos['strike'] <= (strike - Config.STRANGLE_GAP)):
                        conflicts.append(pos)
        
        return conflicts

    def get_positions(self) -> List[PositionType]:
        """Get all positions with directional metadata.
        
        Returns:
            List of position dictionaries
        """
        return self.positions

    def get_positions_by(
        self,
        symbol: Optional[str] = None,
        direction: Optional[str] = None,
        expiry: Optional[datetime.date] = None
    ) -> List[PositionType]:
        """Filter positions by multiple criteria.
        
        Args:
            symbol: Trading symbol to filter
            direction: BUY/SELL direction filter
            expiry: Expiry date filter
            
        Returns:
            Filtered list of positions
        """
        filtered = []
        for pos in self.positions:
            match = True
            if symbol and pos['symbol'] != symbol:
                match = False
            if direction and pos['direction'] != direction:
                match = False
            if expiry and pos['expiry'] != expiry:
                match = False
            if match:
                filtered.append(pos)
        return filtered

    def _get_ltp(self, symbol: str) -> float:
        """Get last traded price with error resilience.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Last traded price or 0.0 if unavailable
        """
        try:
            return self.kite.ltp(f"NFO:{symbol}")[f"NFO:{symbol}"]['last_price']
        except Exception as e:
            logger.error(f"LTP fetch failed for {symbol}: {str(e)}")
            return 0.0

    def has_active_positions(self) -> bool:
        """Check for any non-zero positions.
        
        Returns:
            True if any positions exist, False otherwise
        """
        return any(pos['absolute_quantity'] > 0 for pos in self.positions)

    def get_position(
        self,
        symbol: str,
        direction: Optional[str] = None
    ) -> Optional[PositionType]:
        """Get specific position with optional direction filter.
        
        Args:
            symbol: Trading symbol
            direction: Optional BUY/SELL direction filter
            
        Returns:
            Position dictionary or None if not found
        """
        for pos in self.positions:
            if pos['symbol'] == symbol:
                if not direction or pos['direction'] == direction:
                    return pos
        return None

    def clear_positions(self) -> None:
        """Reset position cache."""
        self.positions = []
        self.last_updated = None

    def get_net_exposure(self) -> Dict[str, float]:
        """Calculate net exposure per instrument type.
        
        Returns:
            Dictionary with CE/PE net exposure values
        """
        exposure = {'CE': 0.0, 'PE': 0.0}
        for pos in self.positions:
            exposure[pos['instrument_type']] += (
                pos['absolute_quantity'] * Config.LOT_SIZE *
                (1 if pos['direction'] == 'SELL' else -1)
            )
        return exposure
