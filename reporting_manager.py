# reporting_manager.py
import json
from datetime import datetime
from pathlib import Path
from config import Config

class ReportingManager:
    def __init__(self, config: Config):
        self.config = config
        self.report_dir = Path(config.LOG_DIR) / "reports"
        self.report_dir.mkdir(exist_ok=True)
        
    def _get_monthly_report_path(self, month_key: str = None):
        month_key = month_key or datetime.now().strftime("%Y-%m")
        return self.report_dir / f"monthly_report_{month_key}.json"
    
    def log_sl_execution(self, order_details: Dict):
        report_path = self._get_monthly_report_path()
        # ... (rest of the method from previous version)
    
    def generate_monthly_report(self, month: str = None) -> Dict:
        report_path = self._get_monthly_report_path(month)
        # ... (rest of the method from previous version)
