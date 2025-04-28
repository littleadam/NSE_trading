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
        self.redirect_url = os.getenv('REDIRECT_URL', 'https://localhost:8080') 
        
        if not self.api_key or not self.api_secret:
            self.logger.error("KiteAuth: API key or secret not found in .env file")
            raise ValueError("API key or secret not found in .env file")
        
        self.kite = KiteConnect(api_key=self.api_key)
        self.logger.info(f"KiteAuth: KiteConnect initialized with API key: {self.api_key}")

    def update_env_variables(self, variables):
         """
         Update multiple environment variables in the .env file
         
         Args:
             variables: Dictionary of variable names and values to update
         """
         env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
         
         # Read the current .env file
         with open(env_path, 'r') as file:
             lines = file.readlines()
         
         # Update the specified keys
         updated_keys = set()
         for i, line in enumerate(lines):
             for key, value in variables.items():
                 if line.startswith(f"{key}="):
                     lines[i] = f"{key}={value}\n"
                     updated_keys.add(key)
                     break
         
         # Add any keys that don't exist
         for key, value in variables.items():
             if key not in updated_keys:
                 lines.append(f"{key}={value}\n")
         
         # Write back to the .env file
         with open(env_path, 'w') as file:
             file.writelines(lines)
         
         self.logger.info(f"KiteAuth: Updated {len(variables)} variables in .env file")

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
        webbrowser.open(login_url)
        
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
