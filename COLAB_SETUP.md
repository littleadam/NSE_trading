# Google Colab Setup for NSE Trading Application

This notebook provides setup instructions for running the NSE Trading Application in Google Colab.

## Setup Instructions

Run the following cells in order to set up and run the application.

## 1. Clone Repository and Install Dependencies

```python
%%writefile setup_colab.py
import os
import sys
import subprocess

def setup_environment():
    """Set up the environment for the NSE Trading Application"""
    print("Setting up environment...")
    
    # Create directory structure
    os.makedirs('NSE_trading/auth', exist_ok=True)
    os.makedirs('NSE_trading/core', exist_ok=True)
    os.makedirs('NSE_trading/utils', exist_ok=True)
    os.makedirs('NSE_trading/tests', exist_ok=True)
    os.makedirs('NSE_trading/logs', exist_ok=True)
    
    # Install required packages
    packages = [
        'kiteconnect',
        'python-dotenv',
        'pandas',
        'numpy',
        'scipy',
        'matplotlib',
        'pytest',
        'pytest-cov',
        'schedule'
    ]
    
    for package in packages:
        print(f"Installing {package}...")
        subprocess.run([sys.executable, '-m', 'pip', 'install', package], check=True)
    
    print("Environment setup complete.")

if __name__ == "__main__":
    setup_environment()
```

Run the setup script:

```python
!python setup_colab.py
```

## 2. Create Configuration File

```python
%%writefile NSE_trading/config.py
class Config:
    def __init__(self):
        # Strategy configuration
        self.straddle = True  # If True, implement short straddle; if False, check strangle
        self.strangle = False  # If True, implement short strangle
        self.bias = 0  # Bias to add to spot price for strike selection
        self.strangle_distance = 1000  # Points away from spot price for strangle legs
        
        # Trading parameters
        self.lot_size = 50  # Number of shares per lot
        self.profit_percentage = 25  # Percentage profit to trigger stop loss and new orders
        self.stop_loss_percentage = 90  # Percentage of original premium to set stop loss
        self.profit_points = 250  # Points of profit to exit all trades on one side (Rs.18750)
        self.shutdown_loss = 12.5  # Percentage of portfolio investment for max loss
        self.adjacency_gap = 200  # Gap for new sell orders when hedge buy orders are in loss
        
        # Hedge configuration
        self.buy_hedge = True  # Whether to place hedge buy orders
        self.hedge_one_lot = True  # If True, buy quantity is one lot; if False, calculate based on sell quantity
        self.far_sell_add = True  # If True, add sell order for same monthly expiry; if False, add next week expiry
        
        # Schedule configuration
        self.start_time = "09:15:00"
        self.end_time = "15:30:00"
        self.run_interval = 5  # Minutes between each run
        self.trading_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        self.holiday_dates = [
            "2025-01-26",  # Republic Day
            "2025-08-15",  # Independence Day
            "2025-10-02",  # Gandhi Jayanti
            # Add more holiday dates as needed
        ]
        self.special_trading_dates = [
            # Add special Saturday/Sunday trading dates here
            # Format: "YYYY-MM-DD"
        ]
        
        # Portfolio configuration
        self.capital_allocated = 500000  # Capital allocated to this strategy
        
        # Authentication
        self.redirect_url = "https://localhost:8080"
        
        # Logging
        self.log_level = "INFO"
        self.log_file = "nse_trading.log"
```

## 3. Create Authentication Module

```python
%%writefile NSE_trading/auth/.env
API_KEY=your_api_key_here
API_SECRET=your_api_secret_here
ACCESS_TOKEN=
REQUEST_TOKEN=
```

```python
%%writefile NSE_trading/auth/kite_auth.py
import os
import time
import logging
from dotenv import load_dotenv
from kiteconnect import KiteConnect
import webbrowser
import json

class KiteAuth:
    def __init__(self, logger):
        """
        Initialize KiteAuth with environment variables and logger
        """
        self.logger = logger
        self.logger.info("KiteAuth: Initializing authentication module")
        
        # Load environment variables
        load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
        
        self.api_key = os.getenv('API_KEY')
        self.api_secret = os.getenv('API_SECRET')
        self.access_token = os.getenv('ACCESS_TOKEN')
        self.request_token = os.getenv('REQUEST_TOKEN')
        self.redirect_url = "https://localhost:8080"
        
        if not self.api_key or not self.api_secret:
            self.logger.error("KiteAuth: API key or secret not found in .env file")
            raise ValueError("API key or secret not found in .env file")
        
        self.kite = KiteConnect(api_key=self.api_key)
        self.logger.info(f"KiteAuth: KiteConnect initialized with API key: {self.api_key}")
    
    def get_login_url(self):
        """
        Get the login URL for Kite Connect
        """
        login_url = self.kite.login_url()
        self.logger.info(f"KiteAuth: Generated login URL: {login_url}")
        return login_url
    
    def generate_access_token(self, request_token=None):
        """
        Generate access token using request token
        """
        if request_token:
            self.request_token = request_token
        
        if not self.request_token:
            self.logger.error("KiteAuth: Request token not provided")
            raise ValueError("Request token not provided")
        
        try:
            data = self.kite.generate_session(self.request_token, api_secret=self.api_secret)
            self.access_token = data["access_token"]
            self.logger.info("KiteAuth: Access token generated successfully")
            
            # Update .env file with new access token
            self._update_env_file('ACCESS_TOKEN', self.access_token)
            self._update_env_file('REQUEST_TOKEN', self.request_token)
            
            # Set access token in kite instance
            self.kite.set_access_token(self.access_token)
            return self.access_token
        except Exception as e:
            self.logger.error(f"KiteAuth: Failed to generate access token: {str(e)}")
            raise
    
    def authenticate(self):
        """
        Complete authentication flow
        """
        self.logger.info("KiteAuth: Starting authentication process")
        
        # Check if we already have a valid access token
        if self.access_token:
            try:
                # Validate the token by making a simple API call
                self.kite.set_access_token(self.access_token)
                profile = self.kite.profile()
                self.logger.info(f"KiteAuth: Using existing access token for user: {profile['user_name']}")
                return self.kite
            except Exception as e:
                self.logger.warning(f"KiteAuth: Existing access token invalid: {str(e)}")
                # Token is invalid, continue with new authentication
        
        # Generate login URL and open in browser
        login_url = self.get_login_url()
        self.logger.info(f"KiteAuth: Opening login URL in browser: {login_url}")
        
        # In Colab, we need to display the URL for the user to click
        from IPython.display import display, HTML
        display(HTML(f'<a href="{login_url}" target="_blank">Click here to login to Kite</a>'))
        print(f"Login URL: {login_url}")
        print("Please click the link above to login to Kite.")
        
        # Wait for user to enter request token
        request_token = input("Enter the request token from the redirect URL: ")
        self.logger.info("KiteAuth: Received request token from user input")
        
        # Generate access token
        self.generate_access_token(request_token)
        self.logger.info("KiteAuth: Authentication completed successfully")
        
        return self.kite
    
    def _update_env_file(self, key, value):
        """
        Update a specific key in the .env file
        """
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
        
        # Read the current .env file
        with open(env_path, 'r') as file:
            lines = file.readlines()
        
        # Update the specific key
        updated = False
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={value}\n"
                updated = True
                break
        
        # If key doesn't exist, add it
        if not updated:
            lines.append(f"{key}={value}\n")
        
        # Write back to the .env file
        with open(env_path, 'w') as file:
            file.writelines(lines)
        
        self.logger.info(f"KiteAuth: Updated {key} in .env file")
```

## 4. Create Core Modules

```python
%%writefile NSE_trading/core/streaming.py
# Copy the content of streaming.py here
```

```python
%%writefile NSE_trading/core/order_manager.py
# Copy the content of order_manager.py here
```

```python
%%writefile NSE_trading/core/expiry_manager.py
# Copy the content of expiry_manager.py here
```

```python
%%writefile NSE_trading/core/risk_manager.py
# Copy the content of risk_manager.py here
```

```python
%%writefile NSE_trading/core/strategy.py
# Copy the content of strategy.py here
```

## 5. Create Utility Modules

```python
%%writefile NSE_trading/utils/logger.py
# Copy the content of logger.py here
```

```python
%%writefile NSE_trading/utils/helpers.py
# Copy the content of helpers.py here
```

```python
%%writefile NSE_trading/utils/position_analyzer.py
# Copy the content of position_analyzer.py here
```

## 6. Create Test Scripts

```python
%%writefile NSE_trading/tests/test_strategies.py
# Copy the content of test_strategies.py here
```

```python
%%writefile NSE_trading/tests/test_core_modules.py
# Copy the content of test_core_modules.py here
```

## 7. Create Main Application and Setup Files

```python
%%writefile NSE_trading/main.py
# Copy the content of main.py here
```

```python
%%writefile NSE_trading/setup.py
# Copy the content of setup.py here
```

## 8. Update API Credentials

Before running the application, update your Zerodha API credentials in the `.env` file:

```python
# Update your API credentials
api_key = input("Enter your Zerodha API key: ")
api_secret = input("Enter your Zerodha API secret: ")

with open('NSE_trading/auth/.env', 'r') as f:
    lines = f.readlines()

updated_lines = []
for line in lines:
    if line.startswith('API_KEY='):
        updated_lines.append(f"API_KEY={api_key}\n")
    elif line.startswith('API_SECRET='):
        updated_lines.append(f"API_SECRET={api_secret}\n")
    else:
        updated_lines.append(line)

with open('NSE_trading/auth/.env', 'w') as f:
    f.writelines(updated_lines)

print("API credentials updated successfully.")
```

## 9. Run Tests

```python
!cd NSE_trading && python -m pytest -xvs tests/test_strategies.py
```

## 10. Run the Application

```python
!cd NSE_trading && python main.py
```

## Notes for Google Colab

1. The application will open a browser window for Zerodha authentication. Since Colab runs in the cloud, you'll need to manually click the login URL and then paste the request token back into Colab.

2. The redirect URL is set to `https://localhost:8080`. After logging in, you'll be redirected to this URL with the request token in the parameters. Copy the request token from the URL and paste it into Colab when prompted.

3. The application is set to run every 5 minutes during market hours. You can adjust this in the `config.py` file.

4. Make sure to keep the Colab notebook running during trading hours. Colab sessions may disconnect after some time of inactivity, so you might need to reconnect and restart the application.

5. All logs are stored in the `logs` directory. You can view them to monitor the application's activity.

## Troubleshooting

1. If you encounter authentication issues, try clearing the access token in the `.env` file and restarting the application.

2. If the application fails to start, check the logs for error messages.

3. If you need to modify the strategy parameters, update the `config.py` file and restart the application.

4. For any other issues, refer to the README.md file or check the logs for detailed error messages.
