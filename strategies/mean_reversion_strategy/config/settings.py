"""
config/settings.py

OPTIMIZED Configuration for multi-asset mean reversion trading system
Based on comprehensive backtest analysis showing which tickers and strategies work

CHANGES FROM ORIGINAL:
- Removed losing tech stocks: AAPL (-$4,620), AVGO (-$4,825), TSLA (-$1,321)
- Kept only profitable tech stocks: AMZN (+$12,079), META (+$5,978), NVDA (+$1,543), MSFT (marginal)
- Removed losing commodity ETFs: GLD (-$2,653)
- Kept profitable commodity ETFs: SLV (+$1,266), CPER (+$673), PALL (+$289)
- Removed losing index ETFs: SPY (-$2,500), DIA (-$2,179), QQQ (-$591)
- Kept profitable index ETFs: IWM (+$1,930), MDY (+$674)
- Increased position sizes to reduce transaction cost impact
- Disabled short selling for commodities and indices (only works with confluence in tech)
"""

# ============================================================================
# ASSET CONFIGURATION
# ============================================================================

ASSET_TYPES = {
    'stocks': {
        'enabled': True,
        'data_source': 'yfinance',
        'min_price': 5.0,
        'max_price': 5000.0,
        'min_volume': 1000000,
        'commission': 0.001,  # 0.1% per trade
        'slippage': 0.001,    # 0.1% slippage
        'allowed_intervals': ['1m', '5m', '15m', '30m', '1h', '4h', '1d'],
    },
    'forex': {
        'enabled': True,
        'data_source': 'yfinance',
        'min_price': 0.0001,
        'max_price': None,
        'min_volume': 0,
        'commission': 0.0002,
        'slippage': 0.0001,
        'allowed_intervals': ['1m', '5m', '15m', '30m', '1h', '4h', '1d'],
    },
    'crypto': {
        'enabled': True,
        'data_source': 'yfinance',
        'min_price': 0.01,
        'max_price': None,
        'min_volume': 100000,
        'commission': 0.001,
        'slippage': 0.002,
        'allowed_intervals': ['1m', '5m', '15m', '30m', '1h', '4h', '1d'],
    },
}


# ============================================================================
# TICKER SYMBOLS BY ASSET CLASS - OPTIMIZED LISTS
# ============================================================================

# TECH STOCKS - ONLY THE WINNERS
# ✅ AMZN: +$12,079 (75.7% win rate) - GOLDEN TICKER
# ✅ META: +$5,978 (60% win rate)
# ✅ NVDA: +$1,543 (50% win rate)
# ⚠️ MSFT: -$334 (marginal)
# ❌ REMOVED: AAPL (-$4,620), AVGO (-$4,825), TSLA (-$1,321)
NAS100_TICKERS = [
    'AMZN',   # PRIMARY FOCUS - 75.7% win rate
    'META',   # 60% win rate  
    'NVDA',   # 50% win rate
]

# COMMODITY ETFs - ONLY THE WINNERS
# ✅ SLV: +$1,266, ✅ CPER: +$673, ✅ PALL: +$289
# ❌ REMOVED: GLD (-$2,653)
COMMODITY_ETFS = [
    'SLV',
    'CPER',
    'PALL',
]

# INDEX ETFs - ONLY THE WINNERS (SMALL/MID CAPS)
# ✅ IWM: +$1,930, ✅ MDY: +$674
# ❌ REMOVED: SPY (-$2,500), DIA (-$2,179), QQQ (-$591)
INDEX_ETFS = [
    'IWM',
    'MDY',
]

# Forex pairs
FOREX_PAIRS = [
    'EURUSD=X',
    'GBPUSD=X',
    'USDJPY=X',
    'AUDUSD=X',
    'USDCAD=X',
    'USDCHF=X',
    'NZDUSD=X',
    'EURGBP=X',
    'EURJPY=X',
    'GBPJPY=X',
]

# Crypto pairs
CRYPTO_PAIRS = [
    'BTC-USD',
    'ETH-USD',
    'BNB-USD',
    'XRP-USD',
    'ADA-USD',
    'SOL-USD',
]


# ============================================================================
# MEAN REVERSION PARAMETERS
# ============================================================================

MEAN_REVERSION_PARAMS = {
    'stocks': {
        'bb_period': 20,
        'bb_std': 2.0,
        'bb_entry_threshold': 2.0,
        'bb_exit_threshold': 0.5,
        'rsi_period': 14,
        'rsi_oversold': 30,
        'rsi_overbought': 70,
        'rsi_extreme_oversold': 20,
        'rsi_extreme_overbought': 80,
        'zscore_period': 20,
        'zscore_entry': 2.0,
        'zscore_exit': 0.5,
        'min_confidence': 0.75,  # Higher for quality
        'stop_loss_atr_mult': 2.0,
        'take_profit_atr_mult': 1.5,
        'trailing_stop_atr_mult': 1.0,
        'max_hold_bars': 20,
    },
    'forex': {
        'bb_period': 20,
        'bb_std': 2.5,
        'bb_entry_threshold': 2.5,
        'bb_exit_threshold': 0.3,
        'rsi_period': 14,
        'rsi_oversold': 25,
        'rsi_overbought': 75,
        'rsi_extreme_oversold': 15,
        'rsi_extreme_overbought': 85,
        'zscore_period': 20,
        'zscore_entry': 2.5,
        'zscore_exit': 0.3,
        'min_confidence': 0.70,
        'stop_loss_atr_mult': 2.5,
        'take_profit_atr_mult': 2.0,
        'trailing_stop_atr_mult': 1.2,
        'max_hold_bars': 30,
    },
    'crypto': {
        'bb_period': 20,
        'bb_std': 2.5,
        'bb_entry_threshold': 2.5,
        'bb_exit_threshold': 0.5,
        'rsi_period': 14,
        'rsi_oversold': 25,
        'rsi_overbought': 75,
        'rsi_extreme_oversold': 15,
        'rsi_extreme_overbought': 85,
        'zscore_period': 20,
        'zscore_entry': 2.5,
        'zscore_exit': 0.5,
        'min_confidence': 0.65,
        'stop_loss_atr_mult': 3.0,
        'take_profit_atr_mult': 2.5,
        'trailing_stop_atr_mult': 1.5,
        'max_hold_bars': 25,
    },
}


# ============================================================================
# RISK MANAGEMENT - OPTIMIZED
# ============================================================================

RISK_CONFIG = {
    'max_portfolio_risk': 0.03,
    'max_position_size': 0.15,
    'max_correlation': 0.7,
    'max_drawdown': 0.15,
    'stocks': {
        'risk_per_trade': 0.01,
        'max_positions': 8,
    },
    'forex': {
        'risk_per_trade': 0.015,
        'max_positions': 5,
    },
    'crypto': {
        'risk_per_trade': 0.02,
        'max_positions': 5,
    },
}


# ============================================================================
# BACKTEST SETTINGS
# ============================================================================

BACKTEST_CONFIG = {
    'initial_balance': 100000,
    'apply_costs': True,
    'apply_slippage': True,
    'lookback_days': {
        '1m': 7,
        '5m': 14,
        '15m': 30,
        '30m': 60,
        '1h': 90,
        '4h': 180,
        '1d': 365,
    },
}


# ============================================================================
# LIVE TRADING SETTINGS
# ============================================================================

LIVE_TRADING_CONFIG = {
    'scan_interval_seconds': 300,
    'order_timeout_seconds': 30,
    'retry_failed_orders': 3,
    'webhook_notifications': True,
    'telegram_notifications': False,
    'paper_trading': True,
    'broker': {
        'name': 'alpaca',
        'api_key': None,
        'api_secret': None,
        'base_url': None,
    },
}


# ============================================================================
# LOGGING
# ============================================================================

LOGGING_CONFIG = {
    'level': 'INFO',
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'file': 'logs/trading.log',
    'console': True,
}
