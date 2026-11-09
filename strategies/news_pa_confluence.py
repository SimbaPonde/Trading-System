"""
News + Price Action Confluence Strategy
Trades only when news sentiment AND price action patterns agree
"""

from datetime import datetime, timedelta
from typing import List
import pandas as pd
import numpy as np

from strategies.price_action_standalone import PriceActionStrategy


class NewsPriceActionConfluenceStrategy:
    """
    Confluence strategy: News sentiment must confirm price action pattern
    
    Rules:
    - BUY pattern + Positive news (sentiment > 0.6) = Take trade (boosted confidence)
    - SELL pattern + Negative news (sentiment < 0.4) = Take trade (boosted confidence)
    - Pattern without news confirmation = Skip
    - Pattern with contradicting news = Skip
    """
    
    def __init__(
        self,
        min_base_confidence: float = 0.70,
        confluence_boost: float = 0.20,
        news_lookback_hours: int = 48,
        min_news_sentiment: float = 0.55
    ):
        self.price_action = PriceActionStrategy(min_confidence=min_base_confidence)
        self.confluence_boost = confluence_boost
        self.news_lookback_hours = news_lookback_hours
        self.min_news_sentiment = min_news_sentiment
    
    def run(
        self,
        tickers: List[str],
        start: datetime,
        end: datetime,
        prices: dict,
        news_df: pd.DataFrame,
        **kwargs
    ) -> pd.DataFrame:
        """
        Run news + price action confluence strategy
        
        Args:
            tickers: List of ticker symbols
            start: Start date
            end: End date
            prices: Dict of {ticker: price_dataframe}
            news_df: DataFrame of news with columns: ticker, time, sentiment, headline
            
        Returns:
            DataFrame of confluence trades only
        """
        # Get price action signals
        pa_signals = self.price_action.run(tickers, start, end, prices)
        
        if pa_signals.empty:
            return pd.DataFrame()
        
        confluence_trades = []
        
        for _, pa_sig in pa_signals.iterrows():
            # Find relevant news for this ticker
            ticker_news = news_df[news_df['ticker'] == pa_sig['ticker']].copy()
            
            if ticker_news.empty:
                continue  # No news, skip
            
            # Find news within lookback window
            signal_time = pd.to_datetime(pa_sig['entry_time'])
            lookback_start = signal_time - timedelta(hours=self.news_lookback_hours)
            
            recent_news = ticker_news[
                (ticker_news['timestamp'] >= lookback_start) &
                (ticker_news['timestamp'] <= signal_time)
            ]
            
            if recent_news.empty:
                continue  # No recent news, skip
            
            # Get most recent news sentiment
            latest_news = recent_news.sort_values('timestamp').iloc[-1]
            news_sentiment = latest_news['polarity']  # Column is 'polarity' not 'sentiment'
            
            # Check for confluence
            is_confluence = False
            
            if pa_sig['side'] == 'BUY':
                # BUY signal needs positive news
                if news_sentiment > self.min_news_sentiment:
                    is_confluence = True
            else:  # SELL
                # SELL signal needs negative news
                if news_sentiment < (1 - self.min_news_sentiment):
                    is_confluence = True
            
            if not is_confluence:
                continue  # No confluence, skip
            
            # CONFLUENCE FOUND - Create enhanced trade
            boosted_confidence = min(pa_sig['confidence'] + self.confluence_boost, 0.98)
            
            confluence_trades.append({
                'ticker': pa_sig['ticker'],
                'entry_time': pa_sig['entry_time'],
                'side': pa_sig['side'],
                'entry_price': pa_sig['entry_price'],
                'stop_loss': pa_sig['stop_loss'],
                'take_profit': pa_sig['take_profit'],
                'confidence': boosted_confidence,
                'strategy': 'news_pa_confluence',
                'pa_pattern': pa_sig['pattern'],
                'pa_reason': pa_sig['reason'],
                'news_sentiment': news_sentiment,
                'news_headline': latest_news['headline'][:60],
                'news_time': latest_news['timestamp'],  # Fixed: 'timestamp' not 'time'
                'confluence_type': 'NEWS_CONFIRMS_PA'
            })
        
        if not confluence_trades:
            return pd.DataFrame()
        
        return pd.DataFrame(confluence_trades)
