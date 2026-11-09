"""
Mean Reversion Strategy Implementation
Multi-indicator approach with proper confirmation
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional
from datetime import datetime
from dataclasses import dataclass

from .config.config import MeanReversionParams, AssetClass


def _as_series(df: pd.DataFrame, col: str) -> pd.Series:
    """Return a 1D Series for a column, even if yfinance produced duplicates/MultiIndex."""
    if col not in df.columns:
        raise KeyError(col)
    s = df[col]
    if isinstance(s, pd.DataFrame):
        # take first column if multiple
        s = s.iloc[:, 0]
    return s

def _to_float(x) -> float:
    """Safely convert pandas scalar to python float; returns nan on failure."""
    try:
        if isinstance(x, (pd.Series, pd.DataFrame, np.ndarray, list, tuple)):
            # take first element
            if hasattr(x, "iloc"):
                x = x.iloc[0]
            elif len(x) > 0:
                x = x[0]
        return float(x)
    except Exception:
        return float("nan")


@dataclass
class Signal:
    """Trading signal"""
    ticker: str
    time: datetime
    side: str  # 'BUY' or 'SELL'
    price: float
    confidence: float
    indicators: Dict[str, float]
    stop_loss: float
    take_profit: float
    reason: str
    asset_class: AssetClass


class MeanReversionIndicators:
    """Calculate mean reversion indicators"""
    
    @staticmethod
    def bollinger_bands(prices: pd.Series, period: int = 20, std_dev: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Calculate Bollinger Bands
        Returns: (upper, middle, lower)
        """
        middle = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        return upper, middle, lower
    
    @staticmethod
    def rsi(prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    @staticmethod
    def zscore(prices: pd.Series, period: int = 20) -> pd.Series:
        """Calculate Z-Score"""
        mean = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()
        zscore = (prices - mean) / std
        return zscore
    
    @staticmethod
    def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        """Calculate Average True Range"""
        high_low = high - low
        high_close = np.abs(high - close.shift())
        low_close = np.abs(low - close.shift())
        
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        atr = true_range.rolling(window=period).mean()
        return atr
    
    @staticmethod
    def volume_ratio(volume: pd.Series, period: int = 20) -> pd.Series:
        """Calculate volume ratio vs average"""
        avg_volume = volume.rolling(window=period).mean()
        return volume / avg_volume


class MeanReversionStrategy:
    """
    Production-ready mean reversion strategy
    
    Entry signals:
    1. Bollinger Band extremes (price near/outside bands)
    2. RSI oversold/overbought
    3. Z-score extreme values
    4. Volume confirmation
    
    Exit signals:
    1. Return to mean (Z-score near 0)
    2. Profit target hit
    3. Stop loss hit
    4. Time-based exit (max hold bars)
    """
    
    def __init__(self, params: MeanReversionParams, asset_class: AssetClass):
        self.params = params
        self.asset_class = asset_class
        
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate all mean reversion indicators
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            DataFrame with indicators added
        """
        df = df.copy()
        
        # Bollinger Bands
        upper, middle, lower = MeanReversionIndicators.bollinger_bands(
            _as_series(df, 'Close'), 
            self.params.bb_period, 
            self.params.bb_std_dev
        )
        df['BB_Upper'] = upper
        df['BB_Middle'] = middle
        df['BB_Lower'] = lower
        df['BB_Width'] = (upper - lower) / middle
        
        # Calculate band position (0 = lower band, 1 = upper band)
        df['BB_Position'] = (_as_series(df, 'Close') - lower) / (upper - lower)
        
        # RSI
        df['RSI'] = MeanReversionIndicators.rsi(_as_series(df, 'Close'), self.params.rsi_period)
        
        # Z-Score
        df['ZScore'] = MeanReversionIndicators.zscore(_as_series(df, 'Close'), self.params.zscore_period)
        
        # ATR for stops
        df['ATR'] = MeanReversionIndicators.atr(
            _as_series(df, 'High'), _as_series(df, 'Low'), _as_series(df, 'Close'), period=14
        )
        
        # Volume indicators
        df['Volume_Ratio'] = MeanReversionIndicators.volume_ratio(_as_series(df, 'Volume'), period=20)
        
        # Moving averages for trend context
        df['MA_20'] = _as_series(df, 'Close').rolling(window=20).mean()
        df['MA_50'] = _as_series(df, 'Close').rolling(window=50).mean()
        
        # Distance from mean (for exits)
        df['Distance_From_Mean'] = (_as_series(df, 'Close') - df['BB_Middle']) / df['BB_Middle']
        
        return df
    
    def check_oversold_conditions(self, row: pd.Series) -> Tuple[bool, float, str]:
        """
        Check if asset is oversold (mean reversion BUY opportunity)
        
        Returns:
            (is_oversold, confidence, reason)
        """
        reasons = []
        confidence = 0.0
        signals = 0
        
        # 1. Bollinger Band check
        if pd.notna(row['BB_Position']):
            if row['BB_Position'] < (1 - self.params.bb_entry_threshold):
                signals += 1
                confidence += 0.35
                reasons.append(f"BB_LOW({row['BB_Position']:.2f})")
        
        # 2. RSI check
        if pd.notna(row['RSI']):
            if row['RSI'] < self.params.rsi_oversold:
                signals += 1
                confidence += 0.30
                reasons.append(f"RSI_OVERSOLD({row['RSI']:.1f})")
        
        # 3. Z-Score check
        if pd.notna(row['ZScore']):
            if row['ZScore'] < -self.params.zscore_entry:
                signals += 1
                confidence += 0.35
                reasons.append(f"ZSCORE_LOW({row['ZScore']:.2f})")
        
        # Volume confirmation (bonus)
        if pd.notna(row['Volume_Ratio']):
            if row['Volume_Ratio'] > self.params.volume_multiplier:
                confidence += 0.15
                reasons.append(f"VOL_SPIKE({row['Volume_Ratio']:.2f}x)")
        
        # Decision: need at least 2 indicators if required
        is_oversold = signals >= 2 if self.params.require_multiple_indicators else signals >= 1
        
        # Normalize confidence
        confidence = min(confidence, 1.0)
        
        reason = " + ".join(reasons) if reasons else "NO_SIGNAL"
        
        return is_oversold, confidence, reason
    
    def check_overbought_conditions(self, row: pd.Series) -> Tuple[bool, float, str]:
        """
        Check if asset is overbought (mean reversion SELL opportunity)
        
        Returns:
            (is_overbought, confidence, reason)
        """
        reasons = []
        confidence = 0.0
        signals = 0
        
        # 1. Bollinger Band check
        if pd.notna(row['BB_Position']):
            if row['BB_Position'] > self.params.bb_entry_threshold:
                signals += 1
                confidence += 0.35
                reasons.append(f"BB_HIGH({row['BB_Position']:.2f})")
        
        # 2. RSI check
        if pd.notna(row['RSI']):
            if row['RSI'] > self.params.rsi_overbought:
                signals += 1
                confidence += 0.30
                reasons.append(f"RSI_OVERBOUGHT({row['RSI']:.1f})")
        
        # 3. Z-Score check
        if pd.notna(row['ZScore']):
            if row['ZScore'] > self.params.zscore_entry:
                signals += 1
                confidence += 0.35
                reasons.append(f"ZSCORE_HIGH({row['ZScore']:.2f})")
        
        # Volume confirmation (bonus)
        if pd.notna(row['Volume_Ratio']):
            if row['Volume_Ratio'] > self.params.volume_multiplier:
                confidence += 0.15
                reasons.append(f"VOL_SPIKE({row['Volume_Ratio']:.2f}x)")
        
        # Decision
        is_overbought = signals >= 2 if self.params.require_multiple_indicators else signals >= 1
        
        # Normalize confidence
        confidence = min(confidence, 1.0)
        
        reason = " + ".join(reasons) if reasons else "NO_SIGNAL"
        
        return is_overbought, confidence, reason
    
    def should_exit_mean_reversion(self, row: pd.Series, entry_side: str) -> Tuple[bool, str]:
        """
        Check if mean reversion trade should exit
        
        Args:
            row: Current bar data
            entry_side: 'BUY' or 'SELL'
            
        Returns:
            (should_exit, reason)
        """
        
        # Check if Z-score has returned to mean
        if pd.notna(row['ZScore']):
            if entry_side == 'BUY':
                # Exit long when price returns above mean
                if row['ZScore'] > -self.params.zscore_exit:
                    return True, f"MEAN_REVERSION_COMPLETE_LONG(Z={row['ZScore']:.2f})"
            else:
                # Exit short when price returns below mean
                if row['ZScore'] < self.params.zscore_exit:
                    return True, f"MEAN_REVERSION_COMPLETE_SHORT(Z={row['ZScore']:.2f})"
        
        # Check if price crossed middle BB
        if pd.notna(row['BB_Position']):
            if entry_side == 'BUY' and row['BB_Position'] > 0.5:
                return True, f"BB_MIDDLE_CROSSED_LONG(POS={row['BB_Position']:.2f})"
            elif entry_side == 'SELL' and row['BB_Position'] < 0.5:
                return True, f"BB_MIDDLE_CROSSED_SHORT(POS={row['BB_Position']:.2f})"
        
        return False, ""
    
    def generate_signals(
        self, 
        df: pd.DataFrame, 
        ticker: str,
        current_bar_only: bool = False
    ) -> List[Signal]:
        """
        Generate trading signals from price data
        
        Args:
            df: DataFrame with OHLCV data and indicators
            ticker: Symbol/ticker
            current_bar_only: Only check the latest bar (for live trading)
            
        Returns:
            List of Signal objects
        """
        signals = []
        
        # Make sure we have indicators
        if 'BB_Position' not in df.columns:
            df = self.calculate_indicators(df)
        
        # Check each bar (or just the last one)
        start_idx = len(df) - 1 if current_bar_only else 0
        
        for i in range(start_idx, len(df)):
            row = df.iloc[i]
            
            # Skip if we don't have complete data
            atr = _to_float(row.get('ATR', np.nan))
            if pd.isna(atr) or atr <= 0:
                continue
            
            # Check for oversold (BUY signal)
            is_oversold, confidence_buy, reason_buy = self.check_oversold_conditions(row)
            
            if is_oversold and confidence_buy > 0.5:
                stop_loss = row['Close'] - (self.params.stop_loss_atr_multiplier * row['ATR'])
                stop_dist = row['Close'] - stop_loss
                take_profit = row['Close'] + (stop_dist * self.params.profit_target_multiplier)
                
                signal = Signal(
                    ticker=ticker,
                    time=row.get('time', row.name) if 'time' in row.index else row.name,
                    side='BUY',
                    price=row['Close'],
                    confidence=confidence_buy,
                    indicators={
                        'bb_position': row.get('BB_Position', np.nan),
                        'rsi': row.get('RSI', np.nan),
                        'zscore': row.get('ZScore', np.nan),
                        'volume_ratio': row.get('Volume_Ratio', np.nan),
                    },
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    reason=reason_buy,
                    asset_class=self.asset_class
                )
                signals.append(signal)
            
            # Check for overbought (SELL signal)
            is_overbought, confidence_sell, reason_sell = self.check_overbought_conditions(row)
            
            if is_overbought and confidence_sell > 0.5:
                stop_loss = row['Close'] + (self.params.stop_loss_atr_multiplier * row['ATR'])
                stop_dist = stop_loss - row['Close']
                take_profit = row['Close'] - (stop_dist * self.params.profit_target_multiplier)
                
                signal = Signal(
                    ticker=ticker,
                    time=row.get('time', row.name) if 'time' in row.index else row.name,
                    side='SELL',
                    price=row['Close'],
                    confidence=confidence_sell,
                    indicators={
                        'bb_position': row.get('BB_Position', np.nan),
                        'rsi': row.get('RSI', np.nan),
                        'zscore': row.get('ZScore', np.nan),
                        'volume_ratio': row.get('Volume_Ratio', np.nan),
                    },
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    reason=reason_sell,
                    asset_class=self.asset_class
                )
                signals.append(signal)
        
        return signals
    
    def filter_signals_by_trend(self, df: pd.DataFrame, signals: List[Signal]) -> List[Signal]:
        """
        Optional: Filter signals to only trade with the trend
        Mean reversion works better in ranging markets, but can be filtered
        """
        filtered = []
        
        for signal in signals:
            # Find corresponding row
            if isinstance(signal.time, datetime):
                mask = df.index == signal.time
            else:
                mask = df['time'] == signal.time
            
            if not mask.any():
                continue
            
            row = df[mask].iloc[0]
            
            # Check trend
            if pd.notna(row.get('MA_20')) and pd.notna(row.get('MA_50')):
                # Uptrend: MA20 > MA50
                uptrend = row['MA_20'] > row['MA_50']
                
                # Only allow BUY in uptrend, SELL in downtrend
                if signal.side == 'BUY' and uptrend:
                    filtered.append(signal)
                elif signal.side == 'SELL' and not uptrend:
                    filtered.append(signal)
            else:
                # If no trend data, keep signal
                filtered.append(signal)
        
        return filtered
