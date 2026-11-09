"""
Mean Reversion + Price Action Confluence Strategy
Trades only when mean reversion AND price action both signal same direction
"""

from datetime import datetime, timedelta
from typing import List
import pandas as pd
import numpy as np

from strategies.price_action_standalone import PriceActionStrategy


class MeanReversionPriceActionConfluenceStrategy:
    """
    Confluence strategy: Mean reversion must confirm price action pattern
    
    Rules:
    - Price action BUY + Mean reversion oversold = Take trade (boosted confidence)
    - Price action SELL + Mean reversion overbought = Take trade (boosted confidence)
    - Signals within 2 days of each other
    - Signals at similar price (within 5%)
    - Pattern without MR confirmation = Skip
    """
    
    def __init__(
        self,
        min_base_confidence: float = 0.70,
        confluence_boost: float = 0.20,
        time_window_days: int = 2,
        price_tolerance_pct: float = 0.05
    ):
        self.price_action = PriceActionStrategy(min_confidence=min_base_confidence)
        self.confluence_boost = confluence_boost
        self.time_window_days = time_window_days
        self.price_tolerance_pct = price_tolerance_pct
    
    def run(
        self,
        tickers: List[str],
        start: datetime,
        end: datetime,
        prices: dict,
        mean_reversion_signals: pd.DataFrame,
        **kwargs
    ) -> pd.DataFrame:
        """
        Run MR + PA confluence strategy
        
        Args:
            tickers: List of ticker symbols
            start: Start date
            end: End date
            prices: Dict of {ticker: price_dataframe}
            mean_reversion_signals: DataFrame from mean reversion strategy
            
        Returns:
            DataFrame of confluence trades only
        """
        # Get price action signals
        pa_signals = self.price_action.run(tickers, start, end, prices)
        
        if pa_signals.empty or mean_reversion_signals.empty:
            return pd.DataFrame()
        
        confluence_trades = []
        matched_mr = set()  # Track matched MR signals to avoid duplicates
        
        for _, pa_sig in pa_signals.iterrows():
            # Find MR signals for same ticker
            mr_signals = mean_reversion_signals[
                mean_reversion_signals['ticker'] == pa_sig['ticker']
            ].copy()
            
            if mr_signals.empty:
                continue
            
            pa_time = pd.to_datetime(pa_sig['entry_time'])
            
            for mr_idx, mr_sig in mr_signals.iterrows():
                # Skip if already matched
                if mr_idx in matched_mr:
                    continue
                
                mr_time = pd.to_datetime(mr_sig['entry_time'])
                
                # Check confluence conditions
                
                # 1. Same direction
                if pa_sig['side'] != mr_sig['side']:
                    continue
                
                # 2. Close in time (within time window)
                time_diff = abs((pa_time - mr_time).days)
                if time_diff > self.time_window_days:
                    continue
                
                # 3. Similar price (within tolerance)
                price_diff = abs(pa_sig['entry_price'] - mr_sig['entry_price']) / pa_sig['entry_price']
                if price_diff > self.price_tolerance_pct:
                    continue
                
                # CONFLUENCE FOUND!
                matched_mr.add(mr_idx)
                
                # Calculate boosted confidence
                base_confidence = (pa_sig['confidence'] + mr_sig['confidence']) / 2
                boosted_confidence = min(base_confidence + self.confluence_boost, 0.98)
                
                # Use tighter stop (safer)
                if pa_sig['side'] == 'BUY':
                    final_stop = max(pa_sig['stop_loss'], mr_sig['stop_loss'])
                else:  # SELL
                    final_stop = min(pa_sig['stop_loss'], mr_sig['stop_loss'])
                
                # Use average target
                final_target = (pa_sig['take_profit'] + mr_sig['take_profit']) / 2
                
                confluence_trades.append({
                    'ticker': pa_sig['ticker'],
                    'entry_time': pa_sig['entry_time'],  # Use PA time (typically more precise)
                    'side': pa_sig['side'],
                    'entry_price': pa_sig['entry_price'],
                    'stop_loss': final_stop,
                    'take_profit': final_target,
                    'confidence': boosted_confidence,
                    'strategy': 'mr_pa_confluence',
                    'pa_pattern': pa_sig['pattern'],
                    'pa_reason': pa_sig['reason'],
                    'mr_reason': mr_sig.get('reason', 'Mean reversion signal'),
                    'mr_indicators': {
                        'rsi': mr_sig.get('rsi', None),
                        'bb_position': mr_sig.get('bb_position', None),
                        'zscore': mr_sig.get('zscore', None)
                    },
                    'confluence_type': 'MR_PA_CONFLUENCE',
                    'time_diff_days': time_diff,
                    'price_diff_pct': price_diff * 100
                })
                
                break  # Only match once per PA signal
        
        if not confluence_trades:
            return pd.DataFrame()
        
        return pd.DataFrame(confluence_trades)
