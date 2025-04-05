import logging

class CircuitBreaker:
    def __init__(self):
        print("Initializing Circuit Breaker...")
        self.tripped = False
        self.error_count = 0
        self.reset_timeout = 300  # 5 minutes

    def record_error(self):
        self.error_count += 1
        print(f"Error recorded. Total errors: {self.error_count}")
        if self.error_count >= 5 and not self.tripped:
            print("!!! CIRCUIT BREAKER TRIPPED !!!")
            self.tripped = True

    def reset(self):
        if self.tripped:
            print("Resetting circuit breaker...")
            self.tripped = False
            self.error_count = 0

class RiskManager:
    def __init__(self, kite_client):
        print("Initializing Risk Manager...")
        self.kite = kite_client
        self.circuit_breaker = CircuitBreaker()

    def check_vix(self):
        try:
            vix_ltp = self.kite.ltp(f"NSE:{TRADE_CONFIG['vix_symbol']}")
            vix = vix_ltp[f"NSE:{TRADE_CONFIG['vix_symbol']}"]['last_price']
            print(f"Current VIX: {vix:.2f}")
            
            if vix > TRADE_CONFIG['vix_threshold']:
                print(f"VIX above {TRADE_CONFIG['vix_threshold']}. Closing all positions!")
                self.close_all_positions()
                
        except Exception as e:
            print(f"Error checking VIX: {str(e)}")
            self.circuit_breaker.record_error()

    def close_all_positions(self):
        print("Closing all positions...")
        try:
            positions = self.kite.positions()['net']
            closed = 0
            for p in positions:
                if p['quantity'] != 0:
                    self.kite.place_order(
                        variety=self.kite.VARIETY_REGULAR,
                        exchange=TRADE_CONFIG['exchange'],
                        tradingsymbol=p['tradingsymbol'],
                        transaction_type="BUY" if p['quantity'] < 0 else "SELL",
                        quantity=abs(p['quantity']),
                        product=TRADE_CONFIG['product_type'],
                        order_type=self.kite.ORDER_TYPE_MARKET
                    )
                    closed += 1
            print(f"Closed {closed} positions successfully")
            
        except Exception as e:
            print(f"Error closing positions: {str(e)}")
            self.circuit_breaker.record_error()

    def monitor_margins(self):
        try:
            margins = self.kite.margins()
            utilized = margins['equity']['utilised']
            available = margins['equity']['available']
            utilization = (utilized / available) * 100
            print(f"Margin Utilization: {utilization:.2f}%")
            
            if utilization > 90:
                print("Margin utilization exceeding 90%!")
                self.circuit_breaker.record_error()
                
        except Exception as e:
            print(f"Margin check error: {str(e)}")
            self.circuit_breaker.record_error()
