%%writefile /content/core/hedge_manager.py
import logging
from datetime import datetime
from typing import Dict

logger = logging.getLogger(__name__)

class HedgeManager:
    def __init__(self, kite_client, position_tracker, config, schedule_manager, order_manager):
        self.kite = kite_client
        self.position_tracker = position_tracker
        self.config = config
        self.schedule_manager = schedule_manager
        self.order_manager = order_manager
        self.hedge_cache = {}

    def maintain_hedges(self):
        """Maintain hedge positions for all active sell positions"""
        logger.info("Starting hedge maintenance")
        try:
            self.position_tracker.refresh()
            sell_positions = self._get_all_sell_positions()
            
            for symbol, position in sell_positions.items():
                self._process_single_hedge(symbol, position)
                
            self._cleanup_hedge_cache()
            
        except Exception as e:
            logger.error(f"Hedge maintenance failed: {str(e)}", exc_info=True)

    def _get_all_sell_positions(self) -> Dict:
        """Retrieve all active sell positions"""
        return {
            sym: pos for sym, pos in self.position_tracker.positions.items() 
            if pos['transaction_type'] == 'SELL'
        }

    def _process_single_hedge(self, symbol: str, position: Dict):
        """Process hedging for a single sell position"""
        try:
            # Parse position details
            option_type = position['option_type']
            sell_strike = self._parse_strike(symbol)
            sell_qty = position['quantity']
            sell_premium = position['average_price']
            
            # Calculate hedge parameters
            hedge_strike = self._calculate_hedge_strike(sell_strike, sell_premium)
            hedge_expiry = self.schedule_manager.get_next_weekly_expiry()
            hedge_symbol = self._generate_hedge_symbol(option_type, hedge_strike, hedge_expiry)
            
            # Check existing hedge
            existing_hedge_qty = self._get_existing_hedge_qty(hedge_symbol)
            required_qty = sell_qty - existing_hedge_qty
            
            if required_qty > 0:
                self._place_hedge_order(hedge_symbol, required_qty, sell_premium)
                self.hedge_cache[hedge_symbol] = datetime.now()

        except Exception as e:
            logger.error(f"Failed to process hedge for {symbol}: {str(e)}")

    def _parse_strike(self, symbol: str) -> int:
        """Extract strike price from tradingsymbol"""
        parts = symbol.split('PE') if 'PE' in symbol else symbol.split('CE')
        return int(parts[0][-5:])

    def _calculate_hedge_strike(self, sell_strike: int, sell_premium: float) -> int:
        """Calculate hedge strike price"""
        return sell_strike + int(sell_premium * self.config['hedge_multiplier'])

    def _generate_hedge_symbol(self, option_type: str, strike: int, expiry: datetime) -> str:
        """Generate NFO symbol for hedge position"""
        expiry_str = expiry.strftime('%d%b%y').upper()
        return f"NIFTY{expiry_str}{strike}{option_type}"

    def _get_existing_hedge_qty(self, hedge_symbol: str) -> int:
        """Get existing hedge quantity for given symbol"""
        position = self.position_tracker.positions.get(hedge_symbol, {})
        return position.get('quantity', 0) if position.get('transaction_type') == 'BUY' else 0

    def _place_hedge_order(self, symbol: str, quantity: int, premium: float):
        """Execute hedge order with safety checks"""
        try:
            logger.info(f"Placing hedge order: {symbol} x {quantity}")
            
            # Validate instrument
            instrument = next((i for i in self.kite.instruments('NFO') 
                             if i['tradingsymbol'] == symbol), None)
            if not instrument:
                raise ValueError(f"Instrument {symbol} not found")
                
            # Validate quantity
            if quantity % instrument['lot_size'] != 0:
                raise ValueError(f"Invalid quantity {quantity} for lot size {instrument['lot_size']}")
            
            # Place order through order manager
            order = self.order_manager.place_order({
                'exchange': 'NFO',
                'tradingsymbol': symbol,
                'transaction_type': 'BUY',
                'quantity': quantity,
                'product': 'MIS',
                'order_type': 'LIMIT',
                'price': self._calculate_hedge_price(premium)
            })
            
            logger.info(f"Hedge order placed: {order['order_id']}")

        except Exception as e:
            logger.error(f"Hedge order failed: {str(e)}")
            raise

    def _calculate_hedge_price(self, sell_premium: float) -> float:
        """Calculate hedge order price with buffer"""
        return round(sell_premium * 0.9, 1)  # 10% below sell premium

    def _cleanup_hedge_cache(self):
        """Remove old entries from hedge cache"""
        cutoff = datetime.now() - timedelta(days=7)
        self.hedge_cache = {k: v for k, v in self.hedge_cache.items() if v > cutoff}
