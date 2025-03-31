# main.py
from kite_utils import KiteManager
from strategy_manager import StrategyManager
from config import Config
import signal
import sys

def main():
    try:
        config = Config()
        config.validate()
        
        kite_mgr = KiteManager(config)
        strategy_mgr = StrategyManager(kite_mgr, config)
        
        signal.signal(signal.SIGINT, lambda s,f: strategy_mgr.stop_strategy())
        print("Starting strategy monitoring...")
        strategy_mgr.start_strategy()
        
    except Exception as e:
        print(f"Fatal error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
