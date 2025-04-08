%%writefile main.py
import time
import schedule
from strategies import OptionStrategy
from utils import is_market_open
import logging
from config import LOGGING_FORMAT, HEARTBEAT_INTERVAL

logging.basicConfig(
    level=logging.INFO,
    format=LOGGING_FORMAT
)

def run_strategy():
    if not is_market_open():
        logging.info("Market closed. Skipping cycle.")
        return
    
    try:
        logging.info("Strategy cycle started")
        strategy = OptionStrategy()
        strategy.manage_strategy()
        logging.info("Strategy cycle completed")
    except Exception as e:
        logging.error(f"Strategy error: {str(e)}", exc_info=True)

if __name__ == "__main__":
    schedule.every(CHECK_INTERVAL).seconds.do(run_strategy)
    
    try:
        while True:
            schedule.run_pending()
            time.sleep(HEARTBEAT_INTERVAL)
    except KeyboardInterrupt:
        logging.info("Shutting down strategy runner")
    except Exception as e:
        logging.error(f"Fatal error: {str(e)}")
