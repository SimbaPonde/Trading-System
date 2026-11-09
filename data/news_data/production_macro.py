"""
Production Macro Event Aggregator
100% API-driven, no manual data, deployment-ready.

Priority:
1. Trading Economics (BEST - has forecast/actual/previous with surprise detection)
2. FRED (BACKUP - official data but no forecasts)

Zero hardcoded calendars. All data from live APIs.
"""

import os
import pandas as pd
from datetime import datetime
from typing import Optional

class ProductionMacroAggregator:
    """
    Production-grade macro event aggregator.
    No toys, no manual data, only live APIs.
    """
    
    def __init__(self):
        self.te_available = False
        self.fred_available = False
        
        # Check Trading Economics
        if os.getenv('TRADING_ECONOMICS_KEY'):
            try:
                from data.trading_economics_client import TradingEconomicsClient
                self.te_client = TradingEconomicsClient()
                self.te_available = True
                print("[MACRO] ✓ Trading Economics initialized (premium source)")
            except Exception as e:
                print(f"[MACRO] Trading Economics init failed: {e}")
        
        # Check FRED
        if os.getenv('FRED_API_KEY'):
            try:
                from fredapi import Fred
                self.fred = Fred(api_key=os.getenv('FRED_API_KEY'))
                self.fred_available = True
                print("[MACRO] ✓ FRED initialized (free backup)")
            except Exception as e:
                print(f"[MACRO] FRED init failed: {e}")
        
        if not self.te_available and not self.fred_available:
            print("[MACRO] ⚠️  No macro sources available")
            print("[MACRO] Get FREE FRED key: https://fred.stlouisfed.org/docs/api/api_key.html")
            print("[MACRO] Or paid TE key: https://tradingeconomics.com/api")
    
    def fetch_events(
        self, 
        start_date: datetime, 
        end_date: datetime,
        event_types: Optional[list] = None
    ) -> pd.DataFrame:
        """
        Fetch macro events with automatic fallback.
        
        Returns standardized DataFrame with columns:
        - timestamp, ticker, event_type, event_name
        - value, forecast, previous
        - polarity (bullish/bearish/neutral)
        - impact, source
        """
        
        all_events = []
        
        # ============================================================
        # SOURCE 1: Trading Economics (Priority)
        # ============================================================
        
        if self.te_available:
            try:
                print(f"[MACRO] Fetching from Trading Economics...")
                
                te_events = self.te_client.get_calendar_events(start_date, end_date)
                
                if not te_events.empty:
                    all_events.append(te_events)
                    print(f"[MACRO] ✓ Trading Economics: {len(te_events)} events")
                    
                    # If TE works, we're golden - it has everything
                    # Still add FRED as redundancy for missing events
                    
            except Exception as e:
                print(f"[MACRO] Trading Economics failed: {e}")
                print("[MACRO] Falling back to FRED...")
        
        # ============================================================
        # SOURCE 2: FRED (Backup/Redundancy)
        # ============================================================
        
        if self.fred_available:
            try:
                print(f"[MACRO] Fetching from FRED...")
                
                fred_events = self._fetch_fred_events(start_date, end_date)
                
                if not fred_events.empty:
                    all_events.append(fred_events)
                    print(f"[MACRO] ✓ FRED: {len(fred_events)} events")
                    
            except Exception as e:
                print(f"[MACRO] FRED failed: {e}")
        
        # ============================================================
        # MERGE AND DEDUPLICATE
        # ============================================================
        
        if not all_events:
            print("[MACRO] ⚠️  No events from any source!")
            return pd.DataFrame(columns=[
                'timestamp', 'ticker', 'event_type', 'event_name',
                'value', 'forecast', 'previous', 'polarity', 'impact', 'source'
            ])
        
        # Combine all sources
        combined = pd.concat(all_events, ignore_index=True)
        
        # Filter by event types if specified
        if event_types is not None:
            if len(event_types) == 0:
                # Empty list means "no events wanted"
                print("[MACRO] ⚠️  include_event_types is empty - no macro events will be used")
                return pd.DataFrame(columns=[
                    'timestamp', 'ticker', 'event_type', 'event_name',
                    'value', 'forecast', 'previous', 'polarity', 'impact', 'source'
                ])
            combined = combined[combined['event_type'].isin(event_types)].copy()
        
        # Deduplicate: same day + event_type
        # Priority: Trading Economics > FRED
        combined['day'] = combined['timestamp'].dt.floor('D')
        priority_map = {'tradingeconomics': 1, 'fred': 2}
        combined['priority'] = combined['source'].map(priority_map).fillna(99)
        
        combined = combined.sort_values(['day', 'event_type', 'priority'])
        combined = combined.drop_duplicates(subset=['day', 'event_type'], keep='first')
        combined = combined.drop(columns=['day', 'priority'])
        
        # Sort by timestamp
        combined = combined.sort_values('timestamp').reset_index(drop=True)
        
        # Summary
        bullish = (combined['polarity'] == 'bullish').sum()
        bearish = (combined['polarity'] == 'bearish').sum()
        neutral = (combined['polarity'] == 'neutral').sum()
        
        print(f"\n[MACRO] ✓ Total: {len(combined)} events")
        print(f"[MACRO]   Bullish: {bullish}, Bearish: {bearish}, Neutral: {neutral}")
        print(f"[MACRO]   Date range: {combined['timestamp'].min().date()} → {combined['timestamp'].max().date()}")
        
        # Show source breakdown
        sources = combined['source'].value_counts()
        print(f"[MACRO]   Sources: {dict(sources)}")
        
        return combined
    
    def _fetch_fred_events(
        self, 
        start_date: datetime, 
        end_date: datetime
    ) -> pd.DataFrame:
        """
        Fetch economic data from FRED API.
        Converts data series into event format with polarity detection.
        """
        
        # Key economic indicators to track
        indicators = {
            'UNRATE': {
                'type': 'UNEMPLOYMENT',
                'name': 'Unemployment Rate',
                'impact': 'High',
                'lower_is_bullish': True  # Lower unemployment = bullish
            },
            'PAYEMS': {
                'type': 'NFP',
                'name': 'Nonfarm Payrolls',
                'impact': 'High',
                'lower_is_bullish': False  # Higher jobs = bullish
            },
            'CPIAUCSL': {
                'type': 'CPI',
                'name': 'Consumer Price Index',
                'impact': 'High',
                'lower_is_bullish': True  # Lower inflation = bullish
            },
            'PCEPI': {
                'type': 'PCE',
                'name': 'PCE Price Index',
                'impact': 'High',
                'lower_is_bullish': True  # Lower inflation = bullish
            },
            'UMCSENT': {
                'type': 'CONSUMER_SENTIMENT',
                'name': 'Consumer Sentiment',
                'impact': 'Medium',
                'lower_is_bullish': False  # Higher sentiment = bullish
            },
            'GDPC1': {
                'type': 'GDP',
                'name': 'Real GDP',
                'impact': 'High',
                'lower_is_bullish': False  # Higher GDP = bullish
            },
            'FEDFUNDS': {
                'type': 'FOMC',
                'name': 'Federal Funds Rate',
                'impact': 'High',
                'lower_is_bullish': True  # Lower rates = bullish
            },
            'ICSA': {
                'type': 'JOBLESS_CLAIMS',
                'name': 'Initial Jobless Claims',
                'impact': 'High',
                'lower_is_bullish': True  # Lower claims = bullish
            },
        }
        
        events = []
        
        for series_id, info in indicators.items():
            try:
                # Fetch data series
                series = self.fred.get_series(
                    series_id,
                    observation_start=start_date,
                    observation_end=end_date
                )
                
                if series is None or len(series) == 0:
                    continue
                
                # Convert to events (one per new data point)
                previous_value = None
                
                for timestamp, value in series.items():
                    if pd.isna(value):
                        continue
                    
                    timestamp = pd.to_datetime(timestamp, utc=True)
                    
                    # Determine polarity based on change
                    polarity = 'neutral'
                    if previous_value is not None:
                        change = float(value) - float(previous_value)
                        
                        if abs(change) > 1e-9:  # Meaningful change
                            if info['lower_is_bullish']:
                                # Lower is better (inflation, unemployment)
                                polarity = 'bullish' if change < 0 else 'bearish'
                            else:
                                # Higher is better (GDP, jobs, sentiment)
                                polarity = 'bullish' if change > 0 else 'bearish'
                    
                    events.append({
                        'timestamp': timestamp,
                        'ticker': 'MACRO',
                        'event_type': info['type'],
                        'event_name': info['name'],
                        'value': float(value),
                        'forecast': None,  # FRED doesn't have forecasts
                        'previous': float(previous_value) if previous_value is not None else None,
                        'polarity': polarity,
                        'impact': info['impact'],
                        'source': 'fred'
                    })
                    
                    previous_value = float(value)
                    
            except Exception as e:
                print(f"[FRED] Error fetching {series_id}: {e}")
                continue
        
        df = pd.DataFrame(events)
        
        if not df.empty:
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
            df = df.sort_values('timestamp').reset_index(drop=True)
        
        return df


# Convenience function for integration
def fetch_macro_events(
    start_date: datetime,
    end_date: datetime,
    event_types: Optional[list] = None
) -> pd.DataFrame:
    """
    Convenience function to fetch macro events.
    Use this in your main backtest code.
    """
    aggregator = ProductionMacroAggregator()
    return aggregator.fetch_events(start_date, end_date, event_types)


if __name__ == '__main__':
    """Test the production macro aggregator"""
    
    from datetime import timedelta
    
    end = datetime.now()
    start = end - timedelta(days=90)
    
    print("=" * 70)
    print("TESTING PRODUCTION MACRO AGGREGATOR")
    print("=" * 70)
    
    events = fetch_macro_events(start, end)
    
    if not events.empty:
        print("\n" + "=" * 70)
        print("SAMPLE EVENTS")
        print("=" * 70)
        
        for _, event in events.head(10).iterrows():
            pol_symbol = "📈" if event['polarity'] == 'bullish' else "📉" if event['polarity'] == 'bearish' else "➡️"
            print(f"{pol_symbol} {event['timestamp'].date()}: {event['event_name']}")
            if event['forecast'] is not None:
                surprise = event['value'] - event['forecast']
                print(f"   Forecast: {event['forecast']:.2f}, Actual: {event['value']:.2f}, Surprise: {surprise:+.2f}")
            else:
                print(f"   Value: {event['value']:.2f}")
        
        print("\n" + "=" * 70)
        print("EVENT BREAKDOWN")
        print("=" * 70)
        
        for event_type in events['event_type'].unique():
            type_events = events[events['event_type'] == event_type]
            bullish = (type_events['polarity'] == 'bullish').sum()
            bearish = (type_events['polarity'] == 'bearish').sum()
            print(f"{event_type}: {len(type_events)} events ({bullish} bullish, {bearish} bearish)")
    else:
        print("\n⚠️  No events found!")
        print("Add API keys to .env file:")
        print("  TRADING_ECONOMICS_KEY=your_key")
        print("  FRED_API_KEY=your_key")