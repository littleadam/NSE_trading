import os
import sys
import logging
import datetime
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from kiteconnect import KiteConnect

class PositionAnalyzer:
    def __init__(self, kite, logger, config, order_manager):
        """
        Initialize PositionAnalyzer with required components
        
        Args:
            kite: Authenticated KiteConnect instance
            logger: Logger instance
            config: Configuration instance
            order_manager: OrderManager instance
        """
        self.kite = kite
        self.logger = logger
        self.config = config
        self.order_manager = order_manager
        self.logger.info("PositionAnalyzer: Initializing position analyzer")
    
    def analyze_current_positions(self):
        """
        Analyze current positions and generate summary
        
        Returns:
            Dictionary with position analysis
        """
        self.logger.info("PositionAnalyzer: Analyzing current positions")
        
        # Refresh positions
        positions = self.order_manager.refresh_positions()
        if not positions or not positions.get('net'):
            self.logger.info("PositionAnalyzer: No positions to analyze")
            return {
                'total_positions': 0,
                'total_pnl': 0,
                'ce_positions': 0,
                'pe_positions': 0,
                'ce_pnl': 0,
                'pe_pnl': 0,
                'buy_positions': 0,
                'sell_positions': 0,
                'buy_pnl': 0,
                'sell_pnl': 0
            }
        
        # Initialize counters
        total_pnl = 0
        ce_positions = 0
        pe_positions = 0
        ce_pnl = 0
        pe_pnl = 0
        buy_positions = 0
        sell_positions = 0
        buy_pnl = 0
        sell_pnl = 0
        
        # Analyze each position
        for position in positions.get('net', []):
            # Skip positions with zero quantity
            if position.get('quantity', 0) == 0:
                continue
            
            # Get position details
            tradingsymbol = position.get('tradingsymbol', '')
            quantity = position.get('quantity', 0)
            pnl = position.get('pnl', 0)
            
            # Update total PnL
            total_pnl += pnl
            
            # Classify by option type
            if tradingsymbol.endswith('CE'):
                ce_positions += 1
                ce_pnl += pnl
            elif tradingsymbol.endswith('PE'):
                pe_positions += 1
                pe_pnl += pnl
            
            # Classify by position type
            if quantity > 0:  # Buy position
                buy_positions += 1
                buy_pnl += pnl
            else:  # Sell position
                sell_positions += 1
                sell_pnl += pnl
        
        # Create analysis summary
        analysis = {
            'total_positions': len(positions.get('net', [])),
            'total_pnl': total_pnl,
            'ce_positions': ce_positions,
            'pe_positions': pe_positions,
            'ce_pnl': ce_pnl,
            'pe_pnl': pe_pnl,
            'buy_positions': buy_positions,
            'sell_positions': sell_positions,
            'buy_pnl': buy_pnl,
            'sell_pnl': sell_pnl
        }
        
        self.logger.info(f"PositionAnalyzer: Analysis complete - Total PnL: {total_pnl}")
        return analysis
    
    def generate_position_report(self, output_file=None):
        """
        Generate a detailed position report
        
        Args:
            output_file: Path to save the report (optional)
            
        Returns:
            DataFrame with position details
        """
        self.logger.info("PositionAnalyzer: Generating position report")
        
        # Refresh positions
        positions = self.order_manager.refresh_positions()
        if not positions or not positions.get('net'):
            self.logger.info("PositionAnalyzer: No positions for report")
            return pd.DataFrame()
        
        # Create DataFrame from positions
        df = pd.DataFrame(positions.get('net', []))
        
        # Add additional columns
        if not df.empty:
            # Calculate profit percentage
            df['profit_percentage'] = df.apply(
                lambda row: self._calculate_profit_percentage(row), axis=1
            )
            
            # Extract option details
            df['option_type'] = df['tradingsymbol'].apply(
                lambda x: 'CE' if x.endswith('CE') else ('PE' if x.endswith('PE') else 'Other')
            )
            
            # Extract expiry from tradingsymbol (simplified)
            df['expiry'] = df['tradingsymbol'].apply(
                lambda x: self._extract_expiry_from_tradingsymbol(x)
            )
            
            # Position type
            df['position_type'] = df['quantity'].apply(
                lambda x: 'Buy' if x > 0 else 'Sell'
            )
        
        # Save to file if specified
        if output_file:
            df.to_csv(output_file, index=False)
            self.logger.info(f"PositionAnalyzer: Report saved to {output_file}")
        
        return df
    
    def visualize_positions(self, output_file=None):
        """
        Create visualization of current positions
        
        Args:
            output_file: Path to save the visualization (optional)
            
        Returns:
            Path to saved visualization or None if no positions
        """
        self.logger.info("PositionAnalyzer: Creating position visualization")
        
        # Get position report
        df = self.generate_position_report()
        
        if df.empty:
            self.logger.info("PositionAnalyzer: No positions to visualize")
            return None
        
        # Create figure with subplots
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        
        # 1. PnL by option type
        if 'option_type' in df.columns and 'pnl' in df.columns:
            pnl_by_type = df.groupby('option_type')['pnl'].sum()
            pnl_by_type.plot(kind='bar', ax=axes[0, 0], color=['green', 'red'])
            axes[0, 0].set_title('PnL by Option Type')
            axes[0, 0].set_ylabel('PnL (₹)')
            
            # Add value labels
            for i, v in enumerate(pnl_by_type):
                axes[0, 0].text(i, v, f'₹{v:.2f}', ha='center', va='bottom' if v > 0 else 'top')
        
        # 2. Position count by type
        if 'position_type' in df.columns:
            pos_count = df['position_type'].value_counts()
            pos_count.plot(kind='pie', ax=axes[0, 1], autopct='%1.1f%%')
            axes[0, 1].set_title('Position Count by Type')
            axes[0, 1].set_ylabel('')
        
        # 3. PnL by expiry
        if 'expiry' in df.columns and 'pnl' in df.columns:
            pnl_by_expiry = df.groupby('expiry')['pnl'].sum()
            pnl_by_expiry.plot(kind='bar', ax=axes[1, 0])
            axes[1, 0].set_title('PnL by Expiry')
            axes[1, 0].set_ylabel('PnL (₹)')
            
            # Add value labels
            for i, v in enumerate(pnl_by_expiry):
                axes[1, 0].text(i, v, f'₹{v:.2f}', ha='center', va='bottom' if v > 0 else 'top')
        
        # 4. Profit percentage distribution
        if 'profit_percentage' in df.columns:
            df['profit_percentage'].plot(kind='hist', ax=axes[1, 1], bins=10)
            axes[1, 1].set_title('Profit Percentage Distribution')
            axes[1, 1].set_xlabel('Profit %')
            axes[1, 1].set_ylabel('Count')
        
        # Adjust layout
        plt.tight_layout()
        
        # Save if output file specified
        if output_file:
            plt.savefig(output_file)
            self.logger.info(f"PositionAnalyzer: Visualization saved to {output_file}")
            return output_file
        
        return None
    
    def _calculate_profit_percentage(self, position):
        """
        Calculate profit percentage for a position
        
        Args:
            position: Position row from DataFrame
            
        Returns:
            Profit percentage
        """
        quantity = position.get('quantity', 0)
        
        if quantity == 0:
            return 0
        
        if quantity > 0:  # Buy position
            buy_price = position.get('buy_price', 0)
            if buy_price == 0:
                return 0
            
            ltp = self.order_manager.get_ltp(position.get('instrument_token'))
            if not ltp:
                return 0
            
            return ((ltp - buy_price) / buy_price) * 100
        else:  # Sell position
            sell_price = position.get('sell_price', 0)
            if sell_price == 0:
                return 0
            
            ltp = self.order_manager.get_ltp(position.get('instrument_token'))
            if not ltp:
                return 0
            
            return ((sell_price - ltp) / sell_price) * 100
    
    def _extract_expiry_from_tradingsymbol(self, tradingsymbol):
        """
        Extract expiry from tradingsymbol (simplified)
        
        Args:
            tradingsymbol: Trading symbol
            
        Returns:
            Expiry string
        """
        try:
            # Assuming format like NIFTY25APR18000CE
            # Extract the date part (25APR)
            if len(tradingsymbol) > 5:
                return tradingsymbol[5:10]
            return "Unknown"
        except Exception:
            return "Unknown"
    
    def get_position_summary(self):
        """
        Get a text summary of current positions
        
        Returns:
            String with position summary
        """
        analysis = self.analyze_current_positions()
        
        summary = [
            "=== Position Summary ===",
            f"Total Positions: {analysis['total_positions']}",
            f"Total PnL: ₹{analysis['total_pnl']:.2f}",
            "",
            "--- By Option Type ---",
            f"CE Positions: {analysis['ce_positions']} (PnL: ₹{analysis['ce_pnl']:.2f})",
            f"PE Positions: {analysis['pe_positions']} (PnL: ₹{analysis['pe_pnl']:.2f})",
            "",
            "--- By Position Type ---",
            f"Buy Positions: {analysis['buy_positions']} (PnL: ₹{analysis['buy_pnl']:.2f})",
            f"Sell Positions: {analysis['sell_positions']} (PnL: ₹{analysis['sell_pnl']:.2f})"
        ]
        
        return "\n".join(summary)
