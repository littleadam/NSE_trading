# strategy_manager.py
from position_manager import PositionManager
from kite_utils import KiteManager
from iron_fly_strategy import IronFlyStrategy
from config import Config

class StrategyManager:
    def __init__(self, kite_manager: KiteManager, config: Config):
        self.kite = kite_manager
        self.config = config
        self.position_manager = PositionManager(kite_manager, config)
        # ... (rest of the class)
