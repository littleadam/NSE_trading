# setup.py
import os
import subprocess
from datetime import datetime
from dotenv import load_dotenv
import time

def clone_repository():
    print("Cloning repository...")
    if not os.path.exists("NSE_trading"):
        subprocess.run(["git", "clone", "https://github.com/littleadam/NSE_trading.git"], check=True)
    os.chdir("NSE_trading/V5")
    print("Repository cloned successfully")

def install_dependencies():
    print("Installing dependencies...")
    dependencies = [
        "kiteconnect",
        "python-dotenv",
        "pandas",
        "schedule",
        "unittest-xml-reporting",
        "coverage"
    ]
    subprocess.run(["pip", "install"] + dependencies, check=True)
    print("Dependencies installed successfully")

def setup_environment():
    print("Setting up environment...")
    
    # Create .env if it doesn't exist
    if not os.path.exists("auth/.env"):
        with open("auth/.env", "w") as f:
            f.write("# Kite Connect Credentials\n")
            f.write("KITE_API_KEY=\n")
            f.write("KITE_API_SECRET=\n")
            f.write("KITE_ACCESS_TOKEN=\n")
    
    # Load environment variables
    load_dotenv("auth/.env")
    
    # Verify API key and secret are set
    if not os.getenv("KITE_API_KEY") or not os.getenv("KITE_API_SECRET"):
        print("\n⚠️ Please configure your Kite Connect credentials in auth/.env")
        print("You need to set KITE_API_KEY and KITE_API_SECRET")
        print("The file has been created at auth/.env")
        return False
    
    return True

def authenticate_kite():
    print("\nAuthenticating with Kite Connect...")
    
    # Import kite_auth after setting up environment
    from auth.kite_auth import KiteAuth
    
    auth = KiteAuth()
    kite = auth.authenticate()
    
    if kite:
        print("✅ Authentication successful!")
        
        # Update .env with new access token
        with open("auth/.env", "r") as f:
            lines = f.readlines()
        
        with open("auth/.env", "w") as f:
            for line in lines:
                if line.startswith("KITE_ACCESS_TOKEN="):
                    f.write(f"KITE_ACCESS_TOKEN={auth.access_token}\n")
                else:
                    f.write(line)
        
        return True
    else:
        print("❌ Authentication failed")
        return False

def run_tests():
    print("\nRunning unit tests...")
    result = subprocess.run([
        "python", "-m", "coverage", "run", 
        "--source=core", "-m", "unittest", 
        "tests/test_strategies.py"
    ])
    
    if result.returncode == 0:
        print("\n✅ All tests passed!")
        
        # Generate coverage report
        subprocess.run(["python", "-m", "coverage", "report", "-m"])
        subprocess.run(["python", "-m", "coverage", "html"])
        
        # Display coverage summary
        with open("htmlcov/index.html", "r") as f:
            print("\nCoverage report generated at htmlcov/index.html")
        
        return True
    else:
        print("\n❌ Some tests failed. Check the output above.")
        return False

def run_main():
    print("\nStarting main trading application...")
    try:
        import main
        trading_system = main.NiftyOptionsTrading()
        trading_system.run()
    except Exception as e:
        print(f"Error running main application: {str(e)}")
        return False
    return True

def main():
    print("🚀 Starting Trading System Setup -", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    try:
        # Step 1: Clone repository
        clone_repository()
        
        # Step 2: Install dependencies
        install_dependencies()
        
        # Step 3: Setup environment
        if not setup_environment():
            return
        
        # Step 4: Authenticate with Kite Connect
        if not authenticate_kite():
            return
        
        # Step 5: Run tests
        if not run_tests():
            print("\nAborting: Tests failed. Fix the issues before running main application.")
            return
        
        # Step 6: Run main application
        print("\n" + "="*50)
        print("Starting Trading Application")
        print("="*50 + "\n")
        
        if not run_main():
            print("\nApplication exited with errors")
        
    except Exception as e:
        print(f"\n❌ Setup failed: {str(e)}")
    finally:
        print("\nSetup completed at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

if __name__ == "__main__":
    main()
