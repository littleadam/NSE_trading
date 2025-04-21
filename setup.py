import os
import sys
import subprocess
import webbrowser
import time
from dotenv import load_dotenv

def clone_repository():
    """Clone the repository if it doesn't exist"""
    if not os.path.exists('NSE_trading'):
        print("Cloning repository...")
        subprocess.run(['git', 'clone', 'https://github.com/your-username/NSE_trading.git'], check=True)
        print("Repository cloned successfully.")
    else:
        print("Repository already exists.")

def install_packages():
    """Install required packages"""
    print("Installing required packages...")
    packages = [
        'kiteconnect',
        'python-dotenv',
        'pandas',
        'numpy',
        'scipy',
        'pytest',
        'pytest-cov'
    ]
    
    for package in packages:
        print(f"Installing {package}...")
        subprocess.run([sys.executable, '-m', 'pip', 'install', package], check=True)
    
    print("All packages installed successfully.")

def create_env_file():
    """Create .env file if it doesn't exist"""
    env_path = os.path.join('NSE_trading', 'auth', '.env')
    
    if not os.path.exists(os.path.dirname(env_path)):
        os.makedirs(os.path.dirname(env_path))
    
    if not os.path.exists(env_path):
        print("Creating .env file...")
        with open(env_path, 'w') as f:
            f.write("API_KEY=your_api_key_here\n")
            f.write("API_SECRET=your_api_secret_here\n")
            f.write("ACCESS_TOKEN=\n")
            f.write("REQUEST_TOKEN=\n")
        print(".env file created successfully.")
    else:
        print(".env file already exists.")

def update_env_file():
    """Update API key and secret in .env file"""
    env_path = os.path.join('NSE_trading', 'auth', '.env')
    
    api_key = input("Enter your Zerodha API key: ")
    api_secret = input("Enter your Zerodha API secret: ")
    
    # Read existing content
    with open(env_path, 'r') as f:
        lines = f.readlines()
    
    # Update API key and secret
    updated_lines = []
    for line in lines:
        if line.startswith('API_KEY='):
            updated_lines.append(f"API_KEY={api_key}\n")
        elif line.startswith('API_SECRET='):
            updated_lines.append(f"API_SECRET={api_secret}\n")
        else:
            updated_lines.append(line)
    
    # Write updated content
    with open(env_path, 'w') as f:
        f.writelines(updated_lines)
    
    print("API key and secret updated in .env file.")

def generate_access_token():
    """Generate Kite access token"""
    sys.path.append(os.path.abspath('NSE_trading'))
    
    from auth.kite_auth import KiteAuth
    from utils.logger import Logger
    from config import Config
    
    config = Config()
    logger = Logger(config).get_logger()
    
    kite_auth = KiteAuth(logger)
    
    print("Generating access token...")
    print("A browser window will open. Please login to your Zerodha account and authorize the application.")
    print("After authorization, you will be redirected to the redirect URL.")
    print("Copy the request token from the URL and paste it here.")
    
    login_url = kite_auth.get_login_url()
    webbrowser.open(login_url)
    
    request_token = input("Enter the request token from the redirect URL: ")
    
    try:
        access_token = kite_auth.generate_access_token(request_token)
        print(f"Access token generated successfully: {access_token}")
        return True
    except Exception as e:
        print(f"Error generating access token: {str(e)}")
        return False

def run_tests():
    """Run test scripts"""
    print("Running tests...")
    result = subprocess.run(['pytest', '-xvs', 'NSE_trading/tests/test_strategies.py'], 
                           capture_output=True, text=True)
    
    print(result.stdout)
    
    if result.returncode == 0:
        print("Tests passed successfully.")
        return True
    else:
        print("Tests failed.")
        return False

def run_main():
    """Run the main application"""
    print("Running main application...")
    subprocess.run(['python', 'NSE_trading/main.py'])

def main():
    """Main setup function"""
    print("Starting setup...")
    
    # Clone repository
    clone_repository()
    
    # Install required packages
    install_packages()
    
    # Create .env file
    create_env_file()
    
    # Update API key and secret
    update_env_file()
    
    # Generate access token
    token_generated = generate_access_token()
    
    if not token_generated:
        print("Failed to generate access token. Setup incomplete.")
        return
    
    # Run tests
    tests_passed = run_tests()
    
    if tests_passed:
        # Run main application
        run_main()
    else:
        print("Tests failed. Not running main application.")

if __name__ == "__main__":
    main()
