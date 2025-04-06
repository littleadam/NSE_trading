from kiteconnect import KiteConnect, KiteTicker
from datetime import datetime
import threading
import time

class TradeManager:
    def __init__(self, api_key, access_token):
        print("Initializing Trade Manager...")
        self.kite = KiteConnect(api_key=api_key)
        self.kite.set_access_token(access_token)
        self.risk_manager = RiskManager(self.kite)
        self.expiry_manager = ExpiryManager()
        self.journal = TradeJournal(self.kite)
        self.ticker = KiteTicker(api_key, access_token)
        self.active_positions = {}
        self.running = False
        
        self.ticker.on_connect = self._on_connect
        self.ticker.on_ticks = self._on_ticks
        self.ticker.on_close = self._on_close

    def _on_connect(self, ws, response):
        print("WebSocket connected")
        self._load_positions()
        if self.active_positions:
            tokens = [p['instrument_token'] for p in self.active_positions.values()]
            self.ticker.subscribe(tokens)
            self.ticker.set_mode(self.ticker.MODE_LTP, tokens)
            print(f"Subscribed to {len(tokens)} instruments")

    def _load_positions(self):
        print("Loading existing positions...")
        try:
            positions = self.kite.positions()['net']
            for p in positions:
                if p['product'] == 'OPT' and p['quantity'] != 0:
                    self.active_positions[p['tradingsymbol']] = {
                        'instrument_token': p['instrument_token'],
                        'quantity': abs(p['quantity']),
                        'average_price': p['average_price'],
                        'transaction_type': 'SELL' if p['quantity'] < 0 else 'BUY'
                    }
            print(f"Loaded {len(self.active_positions)} active positions")
        except Exception as e:
            print(f"Error loading positions: {str(e)}")
            self.risk_manager.circuit_breaker.record_error()

    def start(self):
        print("Starting trading system...")
        self.running = True
        self.ticker.connect(threaded=True)
        
        try:
            while self.running:
                self.risk_manager.monitor_margins()
                self.journal.generate_snapshot()
                time.sleep(60)
        except KeyboardInterrupt:
            self.stop()
        except Exception as e:
            print(f"Runtime error: {str(e)}")
            self.stop()

    def stop(self):
        print("Stopping trading system...")
        self.running = False
        self.ticker.close()
        print("System shutdown complete")

    def _on_ticks(self, ws, ticks):
        try:
            print(f"Processing {len(ticks)} ticks")
            self.risk_manager.check_vix()
            
            for tick in ticks:
                symbol = next((k for k,v in self.active_positions.items() 
                             if v['instrument_token'] == tick['instrument_token']), None)
                if symbol:
                    self._process_tick(symbol, tick['last_price'])
                    
        except Exception as e:
            print(f"Tick processing error: {str(e)}")
            self.risk_manager.circuit_breaker.record_error()

    def _process_tick(self, symbol, price):
        position = self.active_positions[symbol]
        print(f"Processing {symbol} @ {price}")
        
        # Check stop loss
        if price >= position['average_price'] * TRADE_CONFIG['sl_trigger']:
            print(f"SL triggered for {symbol}")
            self._execute_sl(symbol, position)
            
        # Check profit target
        elif (position['average_price'] - price) / position['average_price'] >= TRADE_CONFIG['profit_threshold']:
            print(f"Profit target hit for {symbol}")
            self._rollover_position(symbol)

    def _execute_sl(self, symbol, position):
        try:
            print(f"Executing SL for {symbol}")
            order_id = self.kite.place_order(
                variety=self.kite.VARIETY_STOPLOSS,
                exchange=TRADE_CONFIG['exchange'],
                tradingsymbol=symbol,
                transaction_type="BUY",
                quantity=position['quantity'],
                product=TRADE_CONFIG['product_type'],
                order_type=self.kite.ORDER_TYPE_SL,
                price=position['average_price'] * 0.95,
                trigger_price=position['average_price'] * TRADE_CONFIG['sl_trigger']
            )
            self.journal.record_order({
                'order_id': order_id,
                'tradingsymbol': symbol,
                'transaction_type': 'BUY',
                'quantity': position['quantity'],
                'status': 'SL_TRIGGERED',
                'price': position['average_price'] * 0.95
            })
            del self.active_positions[symbol]
            print(f"SL executed successfully for {symbol}")
            
        except Exception as e:
            print(f"SL execution failed: {str(e)}")
            self.risk_manager.circuit_breaker.record_error()

    def _rollover_position(self, symbol):
        try:
            current = self.active_positions[symbol]
            print(f"Rolling over position for {symbol}")
            
            # Close current position
            self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange=TRADE_CONFIG['exchange'],
                tradingsymbol=symbol,
                transaction_type="BUY",
                quantity=current['quantity'],
                product=TRADE_CONFIG['product_type'],
                order_type=self.kite.ORDER_TYPE_MARKET
            )
            
            # Create new position in next month
            new_symbol = self.expiry_manager.get_next_month_symbol(symbol)
            ltp = self.kite.ltp(f"NFO:{new_symbol}")[f"NFO:{new_symbol}"]['last_price']
            
            order_id = self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange=TRADE_CONFIG['exchange'],
                tradingsymbol=new_symbol,
                transaction_type="SELL",
                quantity=current['quantity'],
                product=TRADE_CONFIG['product_type'],
                order_type=self.kite.ORDER_TYPE_LIMIT,
                price=ltp
            )
            
            # Update position tracking
            order_history = self.kite.order_history(order_id)
            avg_price = order_history[-1]['average_price']
            
            self.active_positions[new_symbol] = {
                'instrument_token': self.kite.instruments("NFO")[0]['instrument_token'],  # Should be looked up properly
                'quantity': current['quantity'],
                'average_price': avg_price,
                'transaction_type': 'SELL'
            }
            
            self.journal.record_order({
                'order_id': order_id,
                'tradingsymbol': new_symbol,
                'transaction_type': 'SELL',
                'quantity': current['quantity'],
                'status': 'ROLLOVER',
                'price': avg_price
            })
            
            print(f"Successfully rolled over to {new_symbol}")
            
        except Exception as e:
            print(f"Rollover failed: {str(e)}")
            self.risk_manager.circuit_breaker.record_error()

    def _on_close(self, ws, code, reason):
        print(f"WebSocket closed (code: {code}, reason: {reason})")
        if self.running:
            print("Attempting reconnect...")
            time.sleep(5)
            self.ticker.connect()
