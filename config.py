# config.py
import os
from dotenv import load_dotenv

class Config:
    def __init__(self):
        load_dotenv()  # Load from .env file
        self.API_KEY = os.getenv("API_KEY")
        self.API_SECRET = os.getenv("API_SECRET")
        self.ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
        self.REQUEST_TOKEN = os.getenv("REQUEST_TOKEN")
        self.LOT_SIZE = int(os.getenv("LOT_SIZE", 15))
        self.LOG_DIR = os.getenv("LOG_DIR", "logs")
        
    def validate(self):
        if not all([self.API_KEY, self.API_SECRET, self.ACCESS_TOKEN]):
            raise ValueError("Missing required environment variables")
