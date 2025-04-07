%%writefile /content/core/trade_manager.py
import time
import logging
from datetime import datetime, timedelta
from kiteconnect import KiteTicker
from kiteconnect.exceptions import NetworkException, KiteException
from .position_tracker import PositionTracker
from .hedge_manager import HedgeManager
from .order_manager import OrderManager
from .schedule_manager import ScheduleManager
from .trade_journal import TradeJournal

logger = logging.getLogger(__name__)

class TradeManager:
    def __init__(self, kite_client, config):
        self.kite = kite_client
        self.config = config
        self.position_tracker = PositionTracker(kite_client)
        self.hedge_manager = HedgeManager(kite_client, self.position_tracker)
        self.order_manager = OrderManager(kite_client, config)
        self.schedule_manager = ScheduleManager(config)
        self.journal = TradeJournal()
        self.ticker = None
        self.running = False
        self.profit_tracker = {'CE': 0, 'PE': 0}
        self.initial_portfolio_value = None

    def start(self):
        """Main entry point to start the trading system"""
        logger.info("Starting trading system")
        self.running = True
        self._initialize_portfolio_value()
        self._connect_websocket()
        
        try:
            while self.running:
                start_time = datetime.now()
                self._run_trading_cycle()
                self._sleep_until_next_run(start_time)
        except KeyboardInterrupt:
            self.stop()
        except Exception as e:
            logger.critical(f"Critical error: {str(e)}", exc_info=True)
            self.stop()

    def _initialize_portfolio_value(self):
        """Capture initial portfolio value for loss calculation"""
        positions = self.kite.positions()['net']
        self.initial_portfolio_value = sum(
            p['average_price'] * abs(p['quantity']) 
            for p in positions 
            if p['product'] == 'OPT'
        )
        logger.info(f"Initial portfolio value: {self.initial_portfolio_value:.2f}")

    def _connect_websocket(self):
        """Initialize WebSocket connection"""
        self.ticker = KiteTicker(
            self.config['api_key'], 
            self.kite.access_token
        )
        self.ticker.on_connect = self._on_ws_connect
        self.ticker.on_ticks = self._on_ws_ticks
        self.ticker.on_close = self._on_ws_close
        self.ticker.connect(threaded=True)
        logger.info("WebSocket connection initiated")

    def _run_trading_cycle(self):
        """Execute one complete trading cycle"""
        if not self.schedule_manager.should_run():
            return

        try:
            # Refresh all data
            self.position_tracker.refresh()
            
            # Check risk conditions first
            if self._check_unrealized_loss():
                return
                
            if self._check_exit_conditions():
                return

            # Core strategy execution
            if not self.position_tracker.has_active_straddle():
                self._place_initial_straddle()
                
            self._manage_profitable_legs()
            self.hedge_manager.maintain_hedges()
            self._log_system_state()

        except NetworkException as ne:
            logger.error(f"Network error: {str(ne)}")
            self._handle_network_error()
        except KiteException as ke:
            logger.error(f"Kite API error: {str(ke)}")
            self._handle_api_error(ke)
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}", exc_info=True)

    def _check_unrealized_loss(self):
        """Check if unrealized loss exceeds threshold"""
        if not self.initial_portfolio_value:
            return False
            
        current_value = sum(
            self.kite.ltp(f"NFO:{symbol}")[f"NFO:{symbol}"]['last_price'] * pos['quantity']
            for symbol, pos in self.position_tracker.positions.items()
        )
        loss_pct = ((self.initial_portfolio_value - current_value) / self.initial_portfolio_value) * 100
        
        if loss_pct >= self.config['max_unrealized_loss_pct']:
            logger.critical(f"Unrealized loss {loss_pct:.2f}% exceeds threshold. Liquidating all positions!")
            self._close_all_positions('CE')
            self._close_all_positions('PE')
            return True
        return False

    def _check_exit_conditions(self):
        """Check if profit targets are met for either side"""
        for option_type in ['CE', 'PE']:
            current_profit = self.position_tracker.calculate_side_profit(option_type)
            self.profit_tracker[option_type] = current_profit
            
            if current_profit >= self.config['exit_points']['net_gain']:
                logger.info(f"{option_type} side reached profit target. Closing all positions.")
                self._close_all_positions(option_type)
                self.profit_tracker[option_type] = 0
                return True
        return False

    def _close_all_positions(self, option_type):
        """Close all positions for given option type"""
        positions = self.position_tracker.get_positions_by_type(option_type)
        for position in positions:
            try:
                self.order_manager.place_exit_order(position)
                self.journal.log_exit(position)
                logger.info(f"Closed {option_type} position: {position['tradingsymbol']}")
            except Exception as e:
                logger.error(f"Failed to close position: {str(e)}")

    def _place_initial_straddle(self):
        """Place new straddle at current spot + bias"""
        nifty_ltp = self.kite.ltp("NSE:NIFTY 50")["NSE:NIFTY 50"]["last_price"]
        strike = self._calculate_straddle_strike(nifty_ltp)
        
        ce_symbol = self._generate_symbol('CE', strike)
        pe_symbol = self._generate_symbol('PE', strike)
        
        try:
            # Place CE sell
            ce_order = self.order_manager.place_sell_order(
                ce_symbol, 
                self.config['lot_size']
            )
            # Place PE sell
            pe_order = self.order_manager.place_sell_order(
                pe_symbol, 
                self.config['lot_size']
            )
            
            self.journal.log_order({
                'order_id': ce_order['order_id'],
                'symbol': ce_symbol,
                'type': 'SELL',
                'quantity': self.config['lot_size'],
                'status': 'OPEN'
            })
            
            self.journal.log_order({
                'order_id': pe_order['order_id'],
                'symbol': pe_symbol,
                'type': 'SELL',
                'quantity': self.config['lot_size'],
                'status': 'OPEN'
            })
            
            logger.info(f"Placed new straddle at {strike} (CE: {ce_symbol}, PE: {pe_symbol})")
            
        except Exception as e:
            logger.error(f"Failed to place straddle: {str(e)}")
            raise

    def _manage_profitable_legs(self):
        """Manage legs that have reached profit target"""
        profitable_legs = self.position_tracker.get_profitable_legs(
            self.config['profit_threshold']
        )
        
        for leg in profitable_legs:
            try:
                # Place SL order
                sl_price = leg['average_price'] * self.config['sl_trigger']
                sl_order = self.order_manager.place_sl_order(
                    leg['tradingsymbol'],
                    leg['quantity'],
                    sl_price
                )
                self.journal.log_sl({
                    'order_id': sl_order['order_id'],
                    'symbol': leg['tradingsymbol'],
                    'trigger_price': sl_price,
                    'quantity': leg['quantity']
                })
                
                # Add new sell order
                new_symbol = self._get_rollover_symbol(leg)
                new_order = self.order_manager.place_sell_order(
                    new_symbol, 
                    leg['quantity']
                )
                self.journal.log_order({
                    'order_id': new_order['order_id'],
                    'symbol': new_symbol,
                    'type': 'SELL',
                    'quantity': leg['quantity'],
                    'status': 'OPEN'
                })
                
                logger.info(f"Rolled {leg['tradingsymbol']} to {new_symbol}")
                
            except Exception as e:
                logger.error(f"Failed to manage profitable leg: {str(e)}")

    def _get_rollover_symbol(self, leg):
        """Generate rollover symbol based on configuration"""
        expiry_date = (
            datetime.strptime(leg['expiry'], '%Y-%m-%d').date()
            if self.config['far_sell_add'] 
            else self.schedule_manager.next_weekly_expiry()
        )
        return self._generate_symbol(
            leg['option_type'],
            leg['strike'],
            expiry_date
        )

    def _log_system_state(self):
        """Record current system state"""
        state = {
            'timestamp': datetime.now().isoformat(),
            'positions': len(self.position_tracker.positions),
            'profit_ce': self.profit_tracker['CE'],
            'profit_pe': self.profit_tracker['PE'],
            'unrealized_pnl': self.position_tracker.calculate_unrealized_pnl(),
            'margin_used': self.kite.margins()['equity']['used']
        }
        self.journal.log_snapshot(state)

    def _sleep_until_next_run(self, cycle_start):
        """Intelligent sleep considering cycle duration"""
        elapsed = (datetime.now() - cycle_start).total_seconds()
        sleep_time = max(
            0,
            self.config['schedule_interval'] * 60 - elapsed
        )
        logger.debug(f"Cycle took {elapsed:.1f}s. Sleeping for {sleep_time:.1f}s")
        time.sleep(sleep_time)

    def _on_ws_connect(self, ws, response):
        """WebSocket connect handler"""
        logger.info("WebSocket connected")
        tokens = [p['instrument_token'] for p in self.position_tracker.positions.values()]
        if tokens:
            self.ticker.subscribe(tokens)
            self.ticker.set_mode(self.ticker.MODE_LTP, tokens)
            logger.debug(f"Subscribed to {len(tokens)} instruments")

    def _on_ws_ticks(self, ws, ticks):
        """WebSocket tick handler"""
        try:
            for tick in ticks:
                self.position_tracker.update_ltp(
                    tick['instrument_token'], 
                    tick['last_price']
                )
                
                # Immediate SL check
                position = self.position_tracker.get_position_by_token(tick['instrument_token'])
                if position and tick['last_price'] >= position['average_price'] * self.config['sl_trigger']:
                    self.order_manager.place_sl_order(
                        position['tradingsymbol'],
                        position['quantity'],
                        position['average_price'] * self.config['sl_trigger']
                    )
        except Exception as e:
            logger.error(f"Tick handling error: {str(e)}")

    def _on_ws_close(self, ws, code, reason):
        """WebSocket close handler"""
        logger.warning(f"WebSocket closed ({code}): {reason}")
        if self.running:
            logger.info("Attempting reconnect in 5 seconds...")
            time.sleep(5)
            self._connect_websocket()

    def stop(self):
        """Graceful shutdown procedure"""
        logger.info("Initiating shutdown sequence...")
        self.running = False
        
        if self.ticker:
            self.ticker.close()
            logger.info("WebSocket connection terminated")
            
        self._close_all_positions('CE')
        self._close_all_positions('PE')
        logger.info("All positions cleared")

    def _calculate_straddle_strike(self, spot):
        """Calculate straddle strike based on spot and bias"""
        return round(spot + self.config['bias'], -50)

    def _generate_symbol(self, option_type, strike, expiry_date):
        """Generate NFO symbol string"""
        expiry_str = expiry_date.strftime('%d%b%y').upper()
        return f"NIFTY{expiry_str}{strike}{option_type}"

    def _handle_network_error(self):
        """Handle network connectivity issues"""
        logger.warning("Network error detected. Retrying in 30 seconds...")
        time.sleep(30)
        self._connect_websocket()

    def _handle_api_error(self, error):
        """Handle Kite API specific errors"""
        if error.code in [403, 429]:
            logger.error("API rate limit exceeded. Cooling down for 1 minute...")
            time.sleep(60)
        elif error.code == 500:
            logger.error("Server error. Retrying in 5 minutes...")
            time.sleep(300)
        else:
            logger.error(f"Unhandled API error (Code {error.code}). Continuing operations...")
