# auth/kite_auth.py
import os
import logging
from dotenv import load_dotenv
from kiteconnect import KiteConnect
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

class KiteAuth:
    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv("KITE_API_KEY")
        self.access_token = os.getenv("KITE_ACCESS_TOKEN")
        self.kite = None

    def _validate_credentials(self):
        """Validate existing credentials through profile API"""
        try:
            self.kite = KiteConnect(api_key=self.api_key)
            self.kite.set_access_token(self.access_token)
            self.kite.profile()
            logger.info("Validated existing credentials successfully")
            return True
        except Exception as e:
            logger.warning(f"Credential validation failed: {str(e)}")
            return False

    def _generate_new_token(self):
        """Complete OAuth2 flow for new token generation"""
        try:
            kite = KiteConnect(api_key=self.api_key)
            
            print("\n\n=== Zerodha Login Required ===")
            print(f"Visit this URL to login: {kite.login_url()}")
            redirect_url = input("Paste redirect URL here: ").strip()
            
            request_token = parse_qs(urlparse(redirect_url).query)["request_token"][0]
            session = kite.generate_session(request_token, api_secret=os.getenv("KITE_API_SECRET"))
            
            self.access_token = session["access_token"]
            self.kite = kite
            self.kite.set_access_token(self.access_token)
            
            # Update environment variables
            os.environ["KITE_ACCESS_TOKEN"] = self.access_token
            logger.info("Successfully generated new access token")
            return True
        except Exception as e:
            logger.error(f"Token generation failed: {str(e)}")
            return False

    def authenticate(self):
        """Main authentication workflow"""
        try:
            if not self.api_key:
                self.api_key = input("Enter KITE_API_KEY: ").strip()
                os.environ["KITE_API_KEY"] = self.api_key
                
            if not self.access_token or not self._validate_credentials():
                if not os.getenv("KITE_API_SECRET"):
                    os.environ["KITE_API_SECRET"] = input("Enter KITE_API_SECRET: ").strip()
                
                if not self._generate_new_token():
                    raise RuntimeError("Authentication failed after multiple attempts")
            
            return self.kite
        except Exception as e:
            logger.critical(f"Critical authentication failure: {str(e)}")
            raise

    def get_kite(self):
        """Get authenticated KiteConnect instance"""
        if not self.kite:
            self.authenticate()
        return self.kite

def init_kite():
    """Initialize and return authenticated KiteConnect instance"""
    auth = KiteAuth()
    return auth.get_kite()
