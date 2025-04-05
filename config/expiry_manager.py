from datetime import datetime, timedelta

class ExpiryManager:
    def __init__(self):
        print("Initializing Expiry Manager...")
        self.current_expiry = self.get_monthly_expiry(datetime.now())
        print(f"Current expiry set to: {self.current_expiry.strftime('%Y-%m-%d')}")

    def get_monthly_expiry(self, date):
        print(f"Calculating monthly expiry for {date.strftime('%Y-%m')}")
        first_day = date.replace(day=1)
        days_needed = (3 * 7) - 1
        third_thursday = first_day + timedelta(days=days_needed - first_day.weekday())
        
        if third_thursday.month != date.month:
            third_thursday -= timedelta(weeks=1)
        
        print(f"Monthly expiry calculated: {third_thursday.strftime('%Y-%m-%d')}")
        return third_thursday

    def get_next_month_symbol(self, current_symbol):
        print(f"Generating next month symbol for {current_symbol}")
        parts = current_symbol.split(TRADE_CONFIG['underlying'])
        strike = parts[1][5:10]
        option_type = parts[1][10:12]
        next_expiry = self.get_monthly_expiry(
            self.current_expiry + timedelta(days=31)
        next_symbol = f"{TRADE_CONFIG['underlying']}" \
                      f"{next_expiry.strftime('%d%b%y').upper()}" \
                      f"{strike}{option_type}"
        print(f"Next month symbol generated: {next_symbol}")
        return next_symbol
