import os
import sys
import logging
import datetime
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import streamlit as st
from kiteconnect import KiteConnect

class Dashboard:
    def __init__(self, kite, logger, config, order_manager, risk_manager, strategy):
        """
        Initialize Dashboard with required components
        
        Args:
            kite: Authenticated KiteConnect instance
            logger: Logger instance
            config: Configuration instance
            order_manager: OrderManager instance
            risk_manager: RiskManager instance
            strategy: Strategy instance
        """
        self.kite = kite
        self.logger = logger
        self.config = config
        self.order_manager = order_manager
        self.risk_manager = risk_manager
        self.strategy = strategy
        self.logger.info("Dashboard: Initializing dashboard")
    
    def run(self):
        """
        Run the Streamlit dashboard
        """
        st.set_page_config(
            page_title="NSE Trading Dashboard",
            page_icon="📈",
            layout="wide",
            initial_sidebar_state="expanded"
        )
        
        self._render_sidebar()
        self._render_main_page()
    
    def _render_sidebar(self):
        """
        Render the sidebar with configuration and controls
        """
        st.sidebar.title("NSE Trading Dashboard")
        st.sidebar.markdown("---")
        
        # Strategy selection
        st.sidebar.subheader("Strategy")
        strategy_type = st.sidebar.radio(
            "Select Strategy",
            ["Short Straddle", "Short Strangle"],
            index=0 if self.config.straddle else 1
        )
        
        # Update config based on selection
        if strategy_type == "Short Straddle":
            self.config.straddle = True
            self.config.strangle = False
        else:
            self.config.straddle = False
            self.config.strangle = True
        
        # Strategy parameters
        st.sidebar.subheader("Parameters")
        self.config.bias = st.sidebar.slider("Strike Bias", -100, 100, self.config.bias, 5)
        self.config.profit_percentage = st.sidebar.slider("Profit %", 5, 50, self.config.profit_percentage, 5)
        self.config.stop_loss_percentage = st.sidebar.slider("Stop Loss %", 50, 100, self.config.stop_loss_percentage, 5)
        
        # Actions
        st.sidebar.subheader("Actions")
        if st.sidebar.button("Refresh Data"):
            st.experimental_rerun()
        
        if st.sidebar.button("Run Strategy Once"):
            self.strategy.execute()
            st.experimental_rerun()
        
        # Status
        st.sidebar.subheader("Status")
        market_status = "Open" if self.risk_manager.is_trading_allowed() else "Closed"
        st.sidebar.metric("Market Status", market_status)
        
        # Show current time
        now = datetime.datetime.now()
        st.sidebar.text(f"Last updated: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    
    def _render_main_page(self):
        """
        Render the main dashboard page
        """
        # Header
        st.title("NSE Trading Dashboard")
        
        # Summary metrics
        self._render_summary_metrics()
        
        # Positions and orders
        col1, col2 = st.columns(2)
        
        with col1:
            self._render_positions()
        
        with col2:
            self._render_orders()
        
        # PnL charts
        self._render_pnl_charts()
        
        # Trade history
        self._render_trade_history()
    
    def _render_summary_metrics(self):
        """
        Render summary metrics
        """
        # Get data
        positions = self.order_manager.refresh_positions()
        
        # Calculate metrics
        total_pnl = sum(p.get('pnl', 0) for p in positions.get('net', []))
        unrealized_pnl = sum(p.get('unrealised_pnl', 0) for p in positions.get('net', []))
        realized_pnl = sum(p.get('realised_pnl', 0) for p in positions.get('net', []))
        
        # Get margin utilization
        margin_used = self.order_manager.get_margin_used() or 0
        margin_percentage = (margin_used / self.config.capital_allocated) * 100 if self.config.capital_allocated else 0
        
        # Display metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total P&L", f"₹{total_pnl:.2f}")
        
        with col2:
            st.metric("Unrealized P&L", f"₹{unrealized_pnl:.2f}")
        
        with col3:
            st.metric("Realized P&L", f"₹{realized_pnl:.2f}")
        
        with col4:
            st.metric("Margin Used", f"₹{margin_used:.2f} ({margin_percentage:.1f}%)")
    
    def _render_positions(self):
        """
        Render positions table
        """
        st.subheader("Current Positions")
        
        # Get positions
        positions = self.order_manager.refresh_positions()
        
        if not positions or not positions.get('net'):
            st.info("No positions found")
            return
        
        # Create DataFrame
        df = pd.DataFrame(positions.get('net', []))
        
        if df.empty:
            st.info("No positions found")
            return
        
        # Add profit percentage
        df['profit_percentage'] = df.apply(
            lambda row: self._calculate_profit_percentage(row), axis=1
        )
        
        # Select columns to display
        display_cols = [
            'tradingsymbol', 'quantity', 'average_price', 'last_price',
            'pnl', 'profit_percentage'
        ]
        
        # Filter columns that exist
        display_cols = [col for col in display_cols if col in df.columns]
        
        # Display table
        st.dataframe(df[display_cols])
    
    def _render_orders(self):
        """
        Render orders table
        """
        st.subheader("Recent Orders")
        
        # Get orders
        orders = self.order_manager.refresh_orders()
        
        if not orders:
            st.info("No orders found")
            return
        
        # Create DataFrame
        df = pd.DataFrame(orders)
        
        if df.empty:
            st.info("No orders found")
            return
        
        # Select columns to display
        display_cols = [
            'tradingsymbol', 'transaction_type', 'quantity', 'price',
            'status', 'order_timestamp'
        ]
        
        # Filter columns that exist
        display_cols = [col for col in display_cols if col in df.columns]
        
        # Sort by timestamp if available
        if 'order_timestamp' in df.columns:
            df = df.sort_values('order_timestamp', ascending=False)
        
        # Display table
        st.dataframe(df[display_cols])
    
    def _render_pnl_charts(self):
        """
        Render P&L charts
        """
        st.subheader("P&L Analysis")
        
        # Get positions
        positions = self.order_manager.refresh_positions()
        
        if not positions or not positions.get('net'):
            st.info("No positions to analyze")
            return
        
        # Create DataFrame
        df = pd.DataFrame(positions.get('net', []))
        
        if df.empty:
            st.info("No positions to analyze")
            return
        
        # Extract option type
        df['option_type'] = df['tradingsymbol'].apply(
            lambda x: 'CE' if x.endswith('CE') else ('PE' if x.endswith('PE') else 'Other')
        )
        
        # Create charts
        col1, col2 = st.columns(2)
        
        with col1:
            # P&L by option type
            if 'option_type' in df.columns and 'pnl' in df.columns:
                st.subheader("P&L by Option Type")
                pnl_by_type = df.groupby('option_type')['pnl'].sum().reset_index()
                
                # Create bar chart
                fig, ax = plt.subplots(figsize=(8, 5))
                bars = ax.bar(pnl_by_type['option_type'], pnl_by_type['pnl'])
                
                # Add value labels
                for bar in bars:
                    height = bar.get_height()
                    ax.text(
                        bar.get_x() + bar.get_width() / 2.,
                        height,
                        f'₹{height:.2f}',
                        ha='center', va='bottom' if height > 0 else 'top'
                    )
                
                ax.set_ylabel('P&L (₹)')
                ax.set_title('P&L by Option Type')
                
                st.pyplot(fig)
        
        with col2:
            # P&L by position type
            if 'quantity' in df.columns and 'pnl' in df.columns:
                st.subheader("P&L by Position Type")
                df['position_type'] = df['quantity'].apply(lambda x: 'Buy' if x > 0 else 'Sell')
                pnl_by_pos_type = df.groupby('position_type')['pnl'].sum().reset_index()
                
                # Create bar chart
                fig, ax = plt.subplots(figsize=(8, 5))
                bars = ax.bar(pnl_by_pos_type['position_type'], pnl_by_pos_type['pnl'])
                
                # Add value labels
                for bar in bars:
                    height = bar.get_height()
                    ax.text(
                        bar.get_x() + bar.get_width() / 2.,
                        height,
                        f'₹{height:.2f}',
                        ha='center', va='bottom' if height > 0 else 'top'
                    )
                
                ax.set_ylabel('P&L (₹)')
                ax.set_title('P&L by Position Type')
                
                st.pyplot(fig)
    
    def _render_trade_history(self):
        """
        Render trade history
        """
        st.subheader("Trade History (This Month)")
        
        # Get orders
        orders = self.order_manager.refresh_orders()
        
        if not orders:
            st.info("No trade history found")
            return
        
        # Create DataFrame
        df = pd.DataFrame(orders)
        
        if df.empty:
            st.info("No trade history found")
            return
        
        # Filter completed orders
        df = df[df['status'] == 'COMPLETE']
        
        # Filter for current month if timestamp available
        if 'order_timestamp' in df.columns:
            current_month = datetime.datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            df['order_timestamp'] = pd.to_datetime(df['order_timestamp'])
            df = df[df['order_timestamp'] >= current_month]
        
        if df.empty:
            st.info("No completed trades this month")
            return
        
        # Select columns to display
        display_cols = [
            'tradingsymbol', 'transaction_type', 'quantity', 'price',
            'order_timestamp'
        ]
        
        # Filter columns that exist
        display_cols = [col for col in display_cols if col in df.columns]
        
        # Sort by timestamp if available
        if 'order_timestamp' in df.columns:
            df = df.sort_values('order_timestamp', ascending=False)
        
        # Display table
        st.dataframe(df[display_cols])
    
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
            buy_price = position.get('average_price', 0)
            if buy_price == 0:
                return 0
            
            last_price = position.get('last_price', 0)
            if not last_price:
                return 0
            
            return ((last_price - buy_price) / buy_price) * 100
        else:  # Sell position
            sell_price = position.get('average_price', 0)
            if sell_price == 0:
                return 0
            
            last_price = position.get('last_price', 0)
            if not last_price:
                return 0
            
            return ((sell_price - last_price) / sell_price) * 100

def run_dashboard(kite, logger, config, order_manager, risk_manager, strategy):
    """
    Run the Streamlit dashboard
    
    Args:
        kite: Authenticated KiteConnect instance
        logger: Logger instance
        config: Configuration instance
        order_manager: OrderManager instance
        risk_manager: RiskManager instance
        strategy: Strategy instance
    """
    dashboard = Dashboard(kite, logger, config, order_manager, risk_manager, strategy)
    dashboard.run()
