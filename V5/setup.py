#!/usr/bin/env python3
# setup.py - Complete Google Colab Setup Script for NSE Trading System

import os
import sys
import subprocess
from datetime import datetime
from getpass import getpass
import urllib.parse
from pathlib import Path

# Constants
REPO_URL = "https://github.com/littleadam/NSE_trading.git"
BRANCH = "main"
V5_DIR = "V5"
REDIRECT_URL = "https://localhost:80"

def install_dependencies():
    """Install all required Python packages"""
    print("⏳ Installing dependencies...")
    packages = [
        'kiteconnect',
        'pandas',
        'python-dotenv',
        'schedule',
        'pytest',
        'coverage',
        'unittest-xml-reporting',
        'pyyaml'
    ]
    subprocess.run([sys.executable, "-m", "pip", "install"] + packages, check=True)
    print("✅ Dependencies installed")

def clone_repository():
    """Clone the repository and navigate to V5 directory"""
    print(f"⏳ Cloning repository {REPO_URL}...")
    if not os.path.exists("NSE_trading"):
        subprocess.run(["git", "clone", "--branch", BRANCH, REPO_URL], check=True)
    os.chdir(f"NSE_trading/{V5_DIR}")
    print("✅ Repository cloned")

def setup_environment():
    """Create necessary environment files"""
    print("⏳ Setting up environment...")
    
    # Create .env file if it doesn't exist
    env_path = Path("auth/.env")
    env_path.parent.mkdir(parents=True, exist_ok=True)
    
    if not env_path.exists():
        # Get credentials from user
        api_key = input("Enter your KITE_API_KEY: ").strip()
        api_secret = getpass("Enter your KITE_API_SECRET: ").strip()
        
        with open(env_path, "w") as f:
            f.write(f"KITE_API_KEY={api_key}\n")
            f.write(f"KITE_API_SECRET={api_secret}\n")
            f.write("KITE_ACCESS_TOKEN=\n")
        
        print("ℹ️ .env file created with API credentials")
    else:
        print("ℹ️ .env file already exists")
    
    print("✅ Environment setup complete")

def generate_access_token():
    """Generate and store access token using KiteAuth"""
    print("⏳ Generating access token...")
    
    # Import kiteauth after dependencies are installed
    from auth.kite_auth import KiteAuth
    from dotenv import load_dotenv
    
    # Load environment variables
    load_dotenv(Path("auth/.env"))
    
    # Initialize KiteAuth
    auth = KiteAuth()
    
    # Override the login URL generation to use our redirect URL
    def mock_login_url(self):
        kite = KiteConnect(api_key=self.api_key)
        return f"{kite.login_url()}?api_key={self.api_key}&redirect={REDIRECT_URL}"
    
    # Monkey patch the login_url method
    from kiteconnect import KiteConnect
    KiteAuth._generate_new_token = mock_login_url
    
    try:
        # Authenticate and get kite client
        kite = auth.authenticate()
        
        # Read back the access token
        with open("auth/.env", "r") as f:
            lines = f.readlines()
        
        # Update the access token in .env
        with open("auth/.env", "w") as f:
            for line in lines:
                if line.startswith("KITE_ACCESS_TOKEN="):
                    f.write(f"KITE_ACCESS_TOKEN={auth.access_token}\n")
                else:
                    f.write(line)
        
        print("✅ Access token generated and stored")
        return True
    except Exception as e:
        print(f"❌ Failed to generate access token: {str(e)}")
        return False

def run_tests():
    """Run the test suite with coverage"""
    print("⏳ Running tests...")
    
    # Install test-specific packages if needed
    subprocess.run([sys.executable, "-m", "pip", "install", "pytest-cov"], check=True)
    
    # Run tests with coverage
    result = subprocess.run([
        sys.executable, "-m", "pytest",
        "tests/test_strategies.py",
        "--cov=core",
        "--cov-report=term",
        "--cov-report=html:htmlcov"
    ])
    
    if result.returncode == 0:
        print("✅ All tests passed")
        return True
    else:
        print("❌ Some tests failed")
        return False

def run_main():
    """Execute the main trading script"""
    print("⏳ Starting main trading script...")
    try:
        subprocess.run([sys.executable, "main.py"], check=True)
        print("✅ Main script completed successfully")
    except subprocess.CalledProcessError as e:
        print(f"❌ Main script failed with error: {e}")
        sys.exit(1)

def main():
    try:
        # Step 1: Install dependencies
        install_dependencies()
        
        # Step 2: Clone repository
        clone_repository()
        
        # Step 3: Setup environment
        setup_environment()
        
        # Step 4: Generate access token
        if not generate_access_token():
            sys.exit(1)
        
        # Step 5: Run tests
        if not run_tests():
            print("❌ Aborting execution due to test failures")
            sys.exit(1)
        
        # Step 6: Run main application
        run_main()
        
    except Exception as e:
        print(f"❌ Setup failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
