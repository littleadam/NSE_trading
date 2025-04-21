import os
import datetime
import pandas as pd
import numpy as np
from kiteconnect import KiteConnect

class Helpers:
    def __init__(self, kite, logger):
        """
        Initialize Helpers with KiteConnect instance
        
        Args:
            kite: Authenticated KiteConnect instance
            logger: Logger instance
        """
        self.kite = kite
        self.logger = logger
        self.logger.info("Helpers: Initializing helpers module")
    
    def round_to_tick_size(self, price, tick_size=0.05):
        """
        Round price to nearest tick size
        
        Args:
            price: Price to round
            tick_size: Tick size (default: 0.05)
            
        Returns:
            Rounded price
        """
        return round(price / tick_size) * tick_size
    
    def get_nifty_spot_price(self):
        """
        Get current Nifty spot price
        
        Returns:
            Current Nifty spot price or None if not available
        """
        try:
            ltp_data = self.kite.ltp(["NSE:NIFTY 50"])
            spot_price = ltp_data["NSE:NIFTY 50"]["last_price"]
            self.logger.info(f"Helpers: Nifty spot price: {spot_price}")
            return spot_price
        except Exception as e:
            self.logger.error(f"Helpers: Failed to get Nifty spot price: {str(e)}")
            return None
    
    def get_instrument_details(self, tradingsymbol, exchange="NFO"):
        """
        Get instrument details by trading symbol
        
        Args:
            tradingsymbol: Trading symbol
            exchange: Exchange (default: NFO)
            
        Returns:
            Instrument details or None if not found
        """
        try:
            instruments = self.kite.instruments(exchange)
            for instrument in instruments:
                if instrument["tradingsymbol"] == tradingsymbol:
                    return instrument
            
            self.logger.warning(f"Helpers: Instrument {tradingsymbol} not found")
            return None
        except Exception as e:
            self.logger.error(f"Helpers: Failed to get instrument details: {str(e)}")
            return None
    
    def get_option_chain(self, expiry_date, underlying="NIFTY"):
        """
        Get option chain for a specific expiry date
        
        Args:
            expiry_date: Expiry date
            underlying: Underlying (default: NIFTY)
            
        Returns:
            DataFrame with option chain or None if not available
        """
        try:
            # Convert expiry_date to datetime.date if it's a string
            if isinstance(expiry_date, str):
                expiry_date = datetime.datetime.strptime(expiry_date, "%Y-%m-%d").date()
            elif isinstance(expiry_date, datetime.datetime):
                expiry_date = expiry_date.date()
            
            # Get all instruments
            instruments = self.kite.instruments("NFO")
            
            # Filter for the underlying and expiry
            filtered_instruments = [
                i for i in instruments 
                if i["name"] == underlying and i["expiry"].date() == expiry_date
            ]
            
            if not filtered_instruments:
                self.logger.warning(f"Helpers: No options found for {underlying} with expiry {expiry_date}")
                return None
            
            # Create DataFrame
            df = pd.DataFrame(filtered_instruments)
            
            # Get current prices
            instrument_tokens = df["instrument_token"].tolist()
            ltp_data = self.kite.ltp([f"NFO:{symbol}" for symbol in df["tradingsymbol"].tolist()])
            
            # Add LTP to DataFrame
            df["ltp"] = df["tradingsymbol"].apply(
                lambda x: ltp_data.get(f"NFO:{x}", {}).get("last_price", 0)
            )
            
            # Pivot to create option chain format
            option_chain = df.pivot_table(
                index="strike", 
                columns="instrument_type", 
                values=["ltp", "instrument_token", "tradingsymbol"]
            )
            
            self.logger.info(f"Helpers: Generated option chain for {underlying} with expiry {expiry_date}")
            return option_chain
        except Exception as e:
            self.logger.error(f"Helpers: Failed to get option chain: {str(e)}")
            return None
    
    def calculate_implied_volatility(self, option_price, spot_price, strike_price, time_to_expiry, option_type="CE", risk_free_rate=0.05):
        """
        Calculate implied volatility using Black-Scholes model
        
        Args:
            option_price: Current option price
            spot_price: Current spot price
            strike_price: Strike price
            time_to_expiry: Time to expiry in years
            option_type: Option type (CE or PE)
            risk_free_rate: Risk-free rate (default: 0.05)
            
        Returns:
            Implied volatility or None if calculation fails
        """
        try:
            from scipy.stats import norm
            from scipy.optimize import newton
            
            def black_scholes(sigma):
                d1 = (np.log(spot_price / strike_price) + (risk_free_rate + 0.5 * sigma ** 2) * time_to_expiry) / (sigma * np.sqrt(time_to_expiry))
                d2 = d1 - sigma * np.sqrt(time_to_expiry)
                
                if option_type == "CE":
                    price = spot_price * norm.cdf(d1) - strike_price * np.exp(-risk_free_rate * time_to_expiry) * norm.cdf(d2)
                else:  # PE
                    price = strike_price * np.exp(-risk_free_rate * time_to_expiry) * norm.cdf(-d2) - spot_price * norm.cdf(-d1)
                
                return price - option_price
            
            # Use Newton-Raphson method to find implied volatility
            implied_vol = newton(black_scholes, x0=0.2, tol=0.0001, maxiter=100)
            
            self.logger.info(f"Helpers: Calculated implied volatility: {implied_vol:.2f}")
            return implied_vol
        except Exception as e:
            self.logger.error(f"Helpers: Failed to calculate implied volatility: {str(e)}")
            return None
    
    def is_market_open(self):
        """
        Check if market is currently open
        
        Returns:
            True if market is open, False otherwise
        """
        now = datetime.datetime.now()
        current_time = now.time()
        current_day = now.strftime("%A")
        
        # Market is closed on weekends
        if current_day in ["Saturday", "Sunday"]:
            return False
        
        # Market hours: 9:15 AM to 3:30 PM
        market_open_time = datetime.time(9, 15, 0)
        market_close_time = datetime.time(15, 30, 0)
        
        return market_open_time <= current_time <= market_close_time
    
    def get_days_to_expiry(self, expiry_date):
        """
        Calculate days to expiry
        
        Args:
            expiry_date: Expiry date
            
        Returns:
            Number of days to expiry
        """
        if isinstance(expiry_date, str):
            expiry_date = datetime.datetime.strptime(expiry_date, "%Y-%m-%d").date()
        elif isinstance(expiry_date, datetime.datetime):
            expiry_date = expiry_date.date()
        
        today = datetime.datetime.now().date()
        days_to_expiry = (expiry_date - today).days
        
        return max(0, days_to_expiry)
    
    def calculate_position_greeks(self, position, spot_price, time_to_expiry, implied_volatility, risk_free_rate=0.05):
        """
        Calculate option Greeks for a position
        
        Args:
            position: Position details
            spot_price: Current spot price
            time_to_expiry: Time to expiry in years
            implied_volatility: Implied volatility
            risk_free_rate: Risk-free rate (default: 0.05)
            
        Returns:
            Dictionary with Greeks (delta, gamma, theta, vega) or None if calculation fails
        """
        try:
            from scipy.stats import norm
            
            # Extract position details
            strike_price = position.get("strike")
            option_type = position.get("instrument_type")
            
            if not strike_price or not option_type:
                self.logger.warning("Helpers: Position details incomplete for Greeks calculation")
                return None
            
            # Calculate d1 and d2
            d1 = (np.log(spot_price / strike_price) + (risk_free_rate + 0.5 * implied_volatility ** 2) * time_to_expiry) / (implied_volatility * np.sqrt(time_to_expiry))
            d2 = d1 - implied_volatility * np.sqrt(time_to_expiry)
            
            # Calculate Greeks
            if option_type == "CE":
                delta = norm.cdf(d1)
                theta = -(spot_price * implied_volatility * norm.pdf(d1)) / (2 * np.sqrt(time_to_expiry)) - risk_free_rate * strike_price * np.exp(-risk_free_rate * time_to_expiry) * norm.cdf(d2)
            else:  # PE
                delta = norm.cdf(d1) - 1
                theta = -(spot_price * implied_volatility * norm.pdf(d1)) / (2 * np.sqrt(time_to_expiry)) + risk_free_rate * strike_price * np.exp(-risk_free_rate * time_to_expiry) * norm.cdf(-d2)
            
            gamma = norm.pdf(d1) / (spot_price * implied_volatility * np.sqrt(time_to_expiry))
            vega = spot_price * np.sqrt(time_to_expiry) * norm.pdf(d1) / 100  # Vega is expressed per 1% change in IV
            
            # Adjust for position quantity
            quantity = position.get("quantity", 0)
            delta *= quantity
            gamma *= quantity
            theta *= quantity
            vega *= quantity
            
            greeks = {
                "delta": delta,
                "gamma": gamma,
                "theta": theta,
                "vega": vega
            }
            
            self.logger.info(f"Helpers: Calculated Greeks for {position.get('tradingsymbol')}: {greeks}")
            return greeks
        except Exception as e:
            self.logger.error(f"Helpers: Failed to calculate Greeks: {str(e)}")
            return None
    
    def format_number(self, number, decimal_places=2):
        """
        Format number with commas and specified decimal places
        
        Args:
            number: Number to format
            decimal_places: Number of decimal places (default: 2)
            
        Returns:
            Formatted number string
        """
        try:
            return f"{number:,.{decimal_places}f}"
        except Exception:
            return str(number)
    
    def calculate_portfolio_margin(self, positions):
        """
        Calculate approximate portfolio margin requirement
        
        Args:
            positions: List of positions
            
        Returns:
            Approximate margin requirement
        """
        try:
            # This is a simplified calculation
            total_margin = 0
            
            for position in positions:
                if position.get("quantity", 0) == 0:
                    continue
                
                instrument_type = position.get("instrument_type")
                quantity = abs(position.get("quantity", 0))
                price = position.get("last_price", 0)
                
                # For short options, margin is higher
                if position.get("quantity", 0) < 0:
                    # Simplified SPAN margin calculation (very approximate)
                    if instrument_type in ["CE", "PE"]:
                        margin = price * quantity * 3  # Multiplier of 3 as a rough estimate
                    else:
                        margin = price * quantity * 1.5
                else:
                    # For long positions, margin is the premium paid
                    margin = price * quantity
                
                total_margin += margin
            
            self.logger.info(f"Helpers: Calculated approximate portfolio margin: {total_margin}")
            return total_margin
        except Exception as e:
            self.logger.error(f"Helpers: Failed to calculate portfolio margin: {str(e)}")
            return None
