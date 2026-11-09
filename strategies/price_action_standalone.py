"""
Price Action Strategy - Standalone
Independent strategy based on technical patterns (support, resistance, pin bars, engulfing)
"""

from datetime import datetime
from typing import List
import pandas as pd
import numpy as np


class PriceActionStrategy:
    """
    Standalone price action strategy
    Trades based on:
    - Support bounces
    - Resistance rejections  
    - Bullish/bearish pin bars
    - Bullish/bearish engulfing patterns
    """
    
    def __init__(
        self,
        min_confidence: float = 0.70,
        atr_stop_multiplier: float = 2.0,
        atr_target_multiplier: float = 3.0,
        use_trend_filter: bool = True
    ):
        self.min_confidence = min_confidence
        self.atr_stop_multiplier = atr_stop_multiplier
        self.atr_target_multiplier = atr_target_multiplier
        self.use_trend_filter = use_trend_filter
    
    def run(
        self,
        tickers: List[str],
        start: datetime,
        end: datetime,
        prices: dict,
        **kwargs
    ) -> pd.DataFrame:
        """
        Run price action strategy
        
        Args:
            tickers: List of ticker symbols
            start: Start date
            end: End date
            prices: Dict of {ticker: price_dataframe}
            
        Returns:
            DataFrame of trades
        """
        all_signals = []
        
        for ticker in tickers:
            if ticker not in prices:
                continue
            
            df = prices[ticker].copy()
            
            if df.empty or len(df) < 50:
                continue
            
            # Calculate indicators
            df = self._calculate_indicators(df)
            
            # Generate signals
            signals = self._generate_signals(ticker, df)
            
            all_signals.extend(signals)
        
        # Convert to DataFrame
        if not all_signals:
            return pd.DataFrame()
        
        trades_df = pd.DataFrame(all_signals)
        trades_df['strategy'] = 'price_action'
        
        return trades_df
    
    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators"""
        # ATR
        df['H-L'] = df['High'] - df['Low']
        df['H-PC'] = abs(df['High'] - df['Close'].shift(1))
        df['L-PC'] = abs(df['Low'] - df['Close'].shift(1))
        df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
        df['ATR'] = df['TR'].rolling(14).mean()
        
        # Moving averages for trend
        df['SMA_20'] = df['Close'].rolling(20).mean()
        df['SMA_50'] = df['Close'].rolling(50).mean()
        
        # Support and resistance (swing highs/lows)
        df['swing_high'] = df['High'].rolling(10, center=True).max()
        df['swing_low'] = df['Low'].rolling(10, center=True).min()
        
        # Recent support/resistance
        df['resistance'] = df['swing_high'].rolling(20).max()
        df['support'] = df['swing_low'].rolling(20).min()
        
        return df
    
    def _generate_signals(self, ticker: str, df: pd.DataFrame) -> List[dict]:
        """Generate price action signals"""
        signals = []
        
        for i in range(50, len(df)):
            row = df.iloc[i]
            prev = df.iloc[i-1]
            
            if pd.isna(row['ATR']) or row['ATR'] <= 0:
                continue
            
            # Determine trend
            if self.use_trend_filter:
                if pd.isna(row['SMA_20']) or pd.isna(row['SMA_50']):
                    continue
                
                if row['SMA_20'] > row['SMA_50']:
                    trend = 'uptrend'
                elif row['SMA_20'] < row['SMA_50']:
                    trend = 'downtrend'
                else:
                    trend = 'neutral'
            else:
                trend = 'neutral'
            
            # Pattern detection
            patterns = self._detect_patterns(df, i)
            
            for pattern in patterns:
                confidence = pattern['confidence']
                
                if confidence < self.min_confidence:
                    continue
                
                # Calculate stops and targets
                if pattern['side'] == 'BUY':
                    stop_loss = row['Close'] - (self.atr_stop_multiplier * row['ATR'])
                    take_profit = row['Close'] + (self.atr_target_multiplier * row['ATR'])
                else:  # SELL
                    stop_loss = row['Close'] + (self.atr_stop_multiplier * row['ATR'])
                    take_profit = row['Close'] - (self.atr_target_multiplier * row['ATR'])
                
                signals.append({
                    'ticker': ticker,
                    'entry_time': row.name,
                    'side': pattern['side'],
                    'entry_price': row['Close'],
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'confidence': confidence,
                    'pattern': pattern['name'],
                    'reason': pattern['reason'],
                    'trend': trend
                })
        
        return signals
    
    def _detect_patterns(self, df: pd.DataFrame, i: int) -> List[dict]:
        """Detect price action patterns"""
        patterns = []
        
        row = df.iloc[i]
        prev = df.iloc[i-1]
        
        # Support bounce
        if not pd.isna(row['support']):
            if row['Low'] <= row['support'] * 1.01 and row['Close'] > row['Open']:
                patterns.append({
                    'name': 'support_bounce',
                    'side': 'BUY',
                    'confidence': 0.80,
                    'reason': f"Support bounce at {row['support']:.2f}"
                })
        
        # Resistance rejection
        if not pd.isna(row['resistance']):
            if row['High'] >= row['resistance'] * 0.99 and row['Close'] < row['Open']:
                patterns.append({
                    'name': 'resistance_rejection',
                    'side': 'SELL',
                    'confidence': 0.80,
                    'reason': f"Resistance rejection at {row['resistance']:.2f}"
                })
        
        # Bullish pin bar
        body = abs(row['Close'] - row['Open'])
        lower_wick = min(row['Open'], row['Close']) - row['Low']
        upper_wick = row['High'] - max(row['Open'], row['Close'])
        
        if lower_wick > body * 2 and lower_wick > upper_wick * 2 and row['Close'] > row['Open']:
            patterns.append({
                'name': 'bullish_pin_bar',
                'side': 'BUY',
                'confidence': 0.85,
                'reason': "Bullish pin bar at support"
            })
        
        # Bearish pin bar
        if upper_wick > body * 2 and upper_wick > lower_wick * 2 and row['Close'] < row['Open']:
            patterns.append({
                'name': 'bearish_pin_bar',
                'side': 'SELL',
                'confidence': 0.85,
                'reason': "Bearish pin bar at resistance"
            })
        
        # Bullish engulfing
        if (prev['Close'] < prev['Open'] and  # Previous was bearish
            row['Close'] > row['Open'] and    # Current is bullish
            row['Open'] <= prev['Close'] and  # Opens at/below prev close
            row['Close'] >= prev['Open']):    # Closes at/above prev open
            
            patterns.append({
                'name': 'bullish_engulfing',
                'side': 'BUY',
                'confidence': 0.90,
                'reason': "Bullish engulfing at support"
            })
        
        # Bearish engulfing
        if (prev['Close'] > prev['Open'] and  # Previous was bullish
            row['Close'] < row['Open'] and    # Current is bearish
            row['Open'] >= prev['Close'] and  # Opens at/above prev close
            row['Close'] <= prev['Open']):    # Closes at/below prev open
            
            patterns.append({
                'name': 'bearish_engulfing',
                'side': 'SELL',
                'confidence': 0.90,
                'reason': "Bearish engulfing at resistance"
            })
        
        return patterns
