"""
Mean Reversion Trading System - Configuration
Supports: NAS100 Stocks, Forex Pairs, Cryptocurrencies
"""

from dataclasses import dataclass
from typing import Dict, List
from enum import Enum


class AssetClass(Enum):
    """Asset classification"""
    STOCK = "stock"
    FOREX = "forex"
    CRYPTO = "crypto"


class TimeFrame(Enum):
    """Trading timeframes"""
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"


@dataclass
class MeanReversionParams:
    """Mean reversion strategy parameters"""
    
    # Bollinger Bands
    bb_period: int = 20
    bb_std_dev: float = 2.0
    bb_entry_threshold: float = 0.95  # Entry when price is at 95% of band
    
    # RSI
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    
    # Z-Score
    zscore_period: int = 20
    zscore_entry: float = 2.0  # Enter when |z-score| > 2
    zscore_exit: float = 0.5   # Exit when |z-score| < 0.5
    
    # Volume confirmation
    volume_multiplier: float = 1.2  # Volume should be 1.2x average
    
    # Mean reversion confirmation
    require_multiple_indicators: bool = True  # Require 2+ indicators agreeing
    
    # Exit strategy
    profit_target_multiplier: float = 1.5  # Target = stop_distance * 1.5
    max_hold_bars: int = 20  # Max bars to hold position
    
    # Risk management
    stop_loss_atr_multiplier: float = 2.0
    position_risk_pct: float = 0.01  # Risk 1% per trade
    max_positions: int = 5


@dataclass
class AssetConfig:
    """Configuration for each asset class"""
    asset_class: AssetClass
    timeframe: TimeFrame
    mean_reversion_params: MeanReversionParams
    
    # Asset-specific settings
    min_volume: float = 0  # Minimum volume (stocks only)
    spread_threshold: float = 0  # Max spread (forex/crypto)
    min_price: float = 0  # Minimum price filter
    max_price: float = float('inf')  # Maximum price filter
    
    # Data source
    data_source: str = "yfinance"  # yfinance, alpaca, ccxt, etc.
    
    # Trading hours (24h for crypto/forex)
    trading_hours: Dict = None
    
    def __post_init__(self):
        if self.trading_hours is None:
            if self.asset_class == AssetClass.STOCK:
                self.trading_hours = {"start": "09:30", "end": "16:00"}
            else:
                self.trading_hours = {"start": "00:00", "end": "23:59"}


# ============================================================================
# ASSET UNIVERSES
# ============================================================================

# NAS100 Tickers (Top 30 most liquid for demo)
NAS100_TICKERS = [
    # Mega cap tech
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA',
    # Other large caps
    'AVGO', 'COST', 'NFLX', 'ADBE', 'CSCO', 'PEP', 'INTC',
    'CMCSA', 'AMD', 'QCOM', 'TXN', 'HON', 'INTU', 'AMGN',
    'AMAT', 'ISRG', 'BKNG', 'ADP', 'GILD', 'SBUX', 'MDLZ',
    'ADI', 'VRTX', 'REGN'
]

# Major Forex Pairs
FOREX_PAIRS = [
    # Majors
    'EURUSD=X', 'GBPUSD=X', 'USDJPY=X', 'AUDUSD=X', 'USDCAD=X', 'USDCHF=X',
    # Crosses
    'EURJPY=X', 'GBPJPY=X', 'EURGBP=X', 'AUDJPY=X', 'EURAUD=X', 'NZDUSD=X'
]

# Major Cryptocurrencies
CRYPTO_PAIRS = [
    'BTC-USD', 'ETH-USD', 'BNB-USD', 'XRP-USD', 'ADA-USD', 
    'SOL-USD', 'DOGE-USD', 'DOT-USD', 'MATIC-USD', 'AVAX-USD',
    'LINK-USD', 'UNI-USD', 'ATOM-USD', 'LTC-USD', 'ETC-USD'
]


# ============================================================================
# DEFAULT CONFIGURATIONS
# ============================================================================

def get_default_config(asset_class: AssetClass, timeframe: TimeFrame = TimeFrame.M15) -> AssetConfig:
    """Get default configuration for asset class"""
    
    if asset_class == AssetClass.STOCK:
        return AssetConfig(
            asset_class=asset_class,
            timeframe=timeframe,
            mean_reversion_params=MeanReversionParams(
                bb_period=20,
                bb_std_dev=2.0,
                rsi_period=14,
                rsi_oversold=30,
                rsi_overbought=70,
                zscore_period=20,
                zscore_entry=2.0,
                profit_target_multiplier=1.5,
                max_hold_bars=20,
                position_risk_pct=0.01,
                max_positions=5
            ),
            min_volume=500000,  # 500K minimum volume
            min_price=5.0,
            data_source="yfinance"
        )
    
    elif asset_class == AssetClass.FOREX:
        return AssetConfig(
            asset_class=asset_class,
            timeframe=timeframe,
            mean_reversion_params=MeanReversionParams(
                bb_period=20,
                bb_std_dev=2.5,  # Wider bands for forex
                rsi_period=14,
                rsi_oversold=25,  # Tighter bounds
                rsi_overbought=75,
                zscore_period=30,  # Longer period
                zscore_entry=2.5,
                profit_target_multiplier=2.0,
                max_hold_bars=30,
                position_risk_pct=0.005,  # Lower risk for forex
                max_positions=3
            ),
            spread_threshold=0.0003,  # 3 pips max spread
            data_source="yfinance"
        )
    
    elif asset_class == AssetClass.CRYPTO:
        return AssetConfig(
            asset_class=asset_class,
            timeframe=timeframe,
            mean_reversion_params=MeanReversionParams(
                bb_period=20,
                bb_std_dev=2.5,  # Wider for volatility
                rsi_period=14,
                rsi_oversold=25,
                rsi_overbought=75,
                zscore_period=20,
                zscore_entry=2.5,
                profit_target_multiplier=2.0,
                max_hold_bars=15,  # Shorter holds for crypto
                position_risk_pct=0.015,  # Higher risk for crypto
                max_positions=4
            ),
            min_price=0.01,
            data_source="yfinance"
        )


# ============================================================================
# RISK PARAMETERS
# ============================================================================

@dataclass
class RiskConfig:
    """Global risk management parameters"""
    
    # Portfolio level
    max_portfolio_risk: float = 0.05  # Max 5% portfolio risk
    max_daily_loss: float = 0.02  # Max 2% daily loss
    max_drawdown: float = 0.10  # Max 10% drawdown
    
    # Position level
    max_position_size: float = 0.20  # Max 20% of portfolio per position
    min_position_size: float = 0.01  # Min 1% of portfolio
    
    # Correlation limits
    max_correlated_positions: int = 3  # Max 3 highly correlated positions
    correlation_threshold: float = 0.7
    
    # Dynamic risk adjustment
    reduce_risk_on_drawdown: bool = True
    risk_reduction_factor: float = 0.5  # Reduce risk by 50% on drawdown
    
    # Circuit breakers
    enable_circuit_breaker: bool = True
    circuit_breaker_loss: float = 0.03  # Stop trading at 3% daily loss
    

# Global risk configuration
RISK_CONFIG = RiskConfig()


# ============================================================================
# BACKTEST PARAMETERS
# ============================================================================

@dataclass
class BacktestConfig:
    """Backtesting configuration"""
    
    initial_balance: float = 100000.0
    
    # Costs
    commission_pct: float = 0.001  # 0.1% commission
    slippage_pct: float = 0.0005   # 0.05% slippage
    
    # Execution
    use_market_orders: bool = True
    fill_on_next_bar: bool = True
    
    # Reporting
    generate_trade_log: bool = True
    generate_equity_curve: bool = True
    generate_metrics: bool = True
    export_results: bool = True


# ============================================================================
# LIVE TRADING PARAMETERS
# ============================================================================

@dataclass
class LiveTradingConfig:
    """Live trading configuration"""
    
    # Broker
    broker_name: str = "alpaca"  # alpaca, ibkr, binance, etc.
    paper_trading: bool = True
    
    # Execution
    order_timeout_seconds: int = 60
    retry_attempts: int = 3
    
    # Monitoring
    check_interval_seconds: int = 60
    max_api_calls_per_minute: int = 60
    
    # Safety
    enable_kill_switch: bool = True
    max_order_size_usd: float = 10000
    require_confirmation: bool = True  # Manual confirmation for orders
    
    # Notifications
    enable_notifications: bool = True
    notification_methods: List[str] = None
    
    def __post_init__(self):
        if self.notification_methods is None:
            self.notification_methods = ["console"]  # console, email, telegram


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_asset_class_from_symbol(symbol: str) -> AssetClass:
    """Detect asset class from symbol"""
    if '-USD' in symbol or '-USDT' in symbol:
        return AssetClass.CRYPTO
    elif '=X' in symbol or 'USD' in symbol[-6:]:
        return AssetClass.FOREX
    else:
        return AssetClass.STOCK


def get_symbols_for_asset_class(asset_class: AssetClass) -> List[str]:
    """Get default symbol list for asset class"""
    if asset_class == AssetClass.STOCK:
        return NAS100_TICKERS
    elif asset_class == AssetClass.FOREX:
        return FOREX_PAIRS
    elif asset_class == AssetClass.CRYPTO:
        return CRYPTO_PAIRS
    return []
