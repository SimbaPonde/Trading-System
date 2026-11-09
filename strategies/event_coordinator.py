"""
Event Coordinator
Manages event detection and blackout periods for mean reversion strategy
"""
from __future__ import annotations
from datetime import timedelta
from typing import Dict, Set
import pandas as pd


class EventCoordinator:
    """
    Coordinates event detection across all strategies to manage mean reversion blackouts.
    """
    
    def __init__(self, blackout_hours: float = 2.0):
        """
        Args:
            blackout_hours: Hours before/after events to blackout mean reversion trades
        """
        self.blackout_hours = blackout_hours
        self.blackout_delta = timedelta(hours=blackout_hours)
        
        # Event storage
        self.news_events: pd.DataFrame = pd.DataFrame()
        self.macro_events: pd.DataFrame = pd.DataFrame()
        self.earnings_events: pd.DataFrame = pd.DataFrame()
        
        # Cache for performance
        self._blackout_periods: Dict[str, Set[pd.Timestamp]] = {}
        
    def register_events(
        self,
        news_df: pd.DataFrame = None,
        macro_df: pd.DataFrame = None,
        earnings_df: pd.DataFrame = None
    ):
        """Register events from various sources"""
        if news_df is not None and not news_df.empty:
            self.news_events = news_df.copy()
            
        if macro_df is not None and not macro_df.empty:
            self.macro_events = macro_df.copy()
            
        if earnings_df is not None and not earnings_df.empty:
            self.earnings_events = earnings_df.copy()
            
        # Clear cache when new events registered
        self._blackout_periods.clear()
        
    def _build_blackout_periods(self, ticker: str = None) -> Set[pd.Timestamp]:
        """
        Build set of timestamps that fall within blackout periods.
        If ticker is provided, only considers events for that ticker.
        
        NOTE: Only macro and earnings events trigger blackouts.
        Regular news events are too frequent and would filter out too many trades.
        """
        blackout_times = set()
        
        # SKIP news events - too many articles (6000+) would blackout almost every day
        # News events are already used by the news/macro strategy for signal generation
        # if not self.news_events.empty:
        #     news_to_check = self.news_events
        #     if ticker:
        #         # Filter news for specific ticker
        #         if 'ticker' in news_to_check.columns:
        #             news_to_check = news_to_check[news_to_check['ticker'] == ticker]
        #     
        #     for ts in pd.to_datetime(news_to_check.get('timestamp', [])):
        #         # Skip NaT values
        #         if pd.notna(ts):
        #             blackout_times.add(ts)
                
        # Process macro events ONLY (affects all tickers) - these are significant market events
        if not self.macro_events.empty:
            for ts in pd.to_datetime(self.macro_events.get('timestamp', [])):
                # Skip NaT values
                if pd.notna(ts):
                    blackout_times.add(ts)
                
        # Process earnings events (ticker-specific, high-impact)
        if not self.earnings_events.empty:
            earnings_to_check = self.earnings_events
            if ticker:
                # Filter earnings for specific ticker
                if 'symbol' in earnings_to_check.columns:
                    earnings_to_check = earnings_to_check[earnings_to_check['symbol'] == ticker]
            
            for ts in pd.to_datetime(earnings_to_check.get('date', [])):
                # Skip NaT values
                if pd.notna(ts):
                    blackout_times.add(ts)
                
        return blackout_times
        
    def is_blackout_period(self, timestamp: pd.Timestamp, ticker: str = None) -> bool:
        """
        Check if given timestamp falls within blackout period for mean reversion.
        
        Args:
            timestamp: Time to check
            ticker: Optional ticker symbol (if None, checks all events)
            
        Returns:
            True if timestamp is within blackout period
        """
        # Normalize timestamp to timezone-naive for comparison
        if hasattr(timestamp, 'tzinfo') and timestamp.tzinfo is not None:
            timestamp = timestamp.tz_localize(None)
        
        # Build cache key
        cache_key = ticker or '__ALL__'
        
        # Build blackout periods if not cached
        if cache_key not in self._blackout_periods:
            self._blackout_periods[cache_key] = self._build_blackout_periods(ticker)
        
        event_times = self._blackout_periods[cache_key]
        
        # Check if timestamp is within blackout_hours of any event
        for event_time in event_times:
            # Normalize event_time to timezone-naive
            if hasattr(event_time, 'tzinfo') and event_time.tzinfo is not None:
                event_time = event_time.tz_localize(None)
                
            time_diff = abs(timestamp - event_time)
            if time_diff <= self.blackout_delta:
                return True
                
        return False
        
    def get_blackout_reason(self, timestamp: pd.Timestamp, ticker: str = None) -> str:
        """
        Get reason for blackout if timestamp is in blackout period.
        
        Returns:
            String describing the reason for blackout, or empty string if not in blackout
        """
        # Normalize timestamp to timezone-naive
        if hasattr(timestamp, 'tzinfo') and timestamp.tzinfo is not None:
            timestamp = timestamp.tz_localize(None)
            
        if not self.is_blackout_period(timestamp, ticker):
            return ""
            
        reasons = []
        
        # Check each event type
        if not self.news_events.empty:
            news_to_check = self.news_events
            if ticker and 'ticker' in news_to_check.columns:
                news_to_check = news_to_check[news_to_check['ticker'] == ticker]
                
            for idx, row in news_to_check.iterrows():
                event_time = pd.to_datetime(row.get('timestamp'))
                # Skip if invalid timestamp
                if event_time is None or pd.isna(event_time):
                    continue
                # Normalize event_time
                if hasattr(event_time, 'tzinfo') and event_time.tzinfo is not None:
                    event_time = event_time.tz_localize(None)
                if abs(timestamp - event_time) <= self.blackout_delta:
                    reasons.append(f"News event at {event_time}")
                    break
                    
        if not self.macro_events.empty:
            for idx, row in self.macro_events.iterrows():
                event_time = pd.to_datetime(row.get('timestamp'))
                # Skip if invalid timestamp
                if event_time is None or pd.isna(event_time):
                    continue
                # Normalize event_time
                if hasattr(event_time, 'tzinfo') and event_time.tzinfo is not None:
                    event_time = event_time.tz_localize(None)
                if abs(timestamp - event_time) <= self.blackout_delta:
                    event_name = row.get('event', 'Macro event')
                    reasons.append(f"{event_name} at {event_time}")
                    break
                    
        if not self.earnings_events.empty:
            earnings_to_check = self.earnings_events
            if ticker and 'symbol' in earnings_to_check.columns:
                earnings_to_check = earnings_to_check[earnings_to_check['symbol'] == ticker]
                
            for idx, row in earnings_to_check.iterrows():
                event_time = pd.to_datetime(row.get('date'))
                # Skip if invalid timestamp
                if event_time is None or pd.isna(event_time):
                    continue
                # Normalize event_time
                if hasattr(event_time, 'tzinfo') and event_time.tzinfo is not None:
                    event_time = event_time.tz_localize(None)
                if abs(timestamp - event_time) <= self.blackout_delta:
                    reasons.append(f"Earnings at {event_time}")
                    break
                    
        return " | ".join(reasons) if reasons else "Event nearby"
        
    def get_statistics(self) -> Dict:
        """Get statistics about registered events"""
        return {
            'news_events': len(self.news_events),
            'macro_events': len(self.macro_events),
            'earnings_events': len(self.earnings_events),
            'blackout_hours': self.blackout_hours,
        }
