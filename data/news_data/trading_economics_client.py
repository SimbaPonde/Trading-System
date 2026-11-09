"""
Trading Economics API Integration - PRODUCTION READY
Real macro events with forecast/actual/previous

Setup:
1. Get API key: https://tradingeconomics.com/api/
2. Add to .env: TRADING_ECONOMICS_KEY=your_key_here
3. Install: pip install requests

Free tier: 500 requests/month
Paid: $79-$249/month for production
"""

import os
import requests
import pandas as pd
from datetime import datetime
from typing import List, Dict, Optional

class TradingEconomicsClient:
    """
    Professional macro event client using Trading Economics API.
    
    This gives you REAL data with forecast/actual/previous!
    Markets trade on surprises - this captures them.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('TRADING_ECONOMICS_KEY')
        self.base_url = 'https://api.tradingeconomics.com'
        
        if not self.api_key:
            raise ValueError("Trading Economics API key required. Get one at: https://tradingeconomics.com/api/")
    
    def get_calendar_events(
        self, 
        start_date: datetime, 
        end_date: datetime, 
        country: str = 'united states'
    ) -> pd.DataFrame:
        """
        Get economic calendar events with forecast/actual/previous.
        
        This is the KEY difference from FRED - you get the surprise!
        
        Args:
            start_date: Start date for events
            end_date: End date for events
            country: Country name (default: 'united states')
        
        Returns:
            DataFrame with columns:
            - timestamp: Event time
            - event_type: CPI, NFP, FOMC, etc.
            - event_name: Full event name
            - value: Actual value
            - forecast: Expected value
            - previous: Previous value
            - polarity: bullish/bearish/neutral (based on surprise)
            - impact: High/Medium/Low
            - source: 'tradingeconomics'
        """
        
        # Format dates as YYYY-MM-DD
        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')
        
        # API endpoint - use generic calendar endpoint (works with free tier)
        url = f'{self.base_url}/calendar'
        
        params = {
            'c': self.api_key,
            'd1': start_str,
            'd2': end_str,
            'format': 'json'
        }
        
        print(f"[TRADING ECONOMICS] Fetching events from {start_str} to {end_str}...")
        
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            print(f"[TRADING ECONOMICS] Error: {e}")
            return pd.DataFrame()
        
        if not data:
            print("[TRADING ECONOMICS] No events returned")
            return pd.DataFrame()
        
        events = []
        
        for event in data:
            # Filter to US events only (since API returns all countries with free tier)
            event_country = event.get('Country', '').lower()
            if event_country not in ['united states', 'us', 'usa']:
                continue
            
            # Skip if no actual value
            if event.get('Actual') is None:
                continue
            
            # Map to standardized schema
            event_obj = {
                'timestamp': pd.to_datetime(event['Date']),
                'ticker': 'MACRO',
                'event_type': self._map_event_type(event.get('Category', '')),
                'event_name': event.get('Event', 'Unknown'),
                'value': float(event['Actual']) if event.get('Actual') is not None else None,
                'forecast': float(event['Forecast']) if event.get('Forecast') is not None else None,
                'previous': float(event['Previous']) if event.get('Previous') is not None else None,
                'polarity': self._calculate_polarity(event),
                'impact': event.get('Importance', 'Medium'),
                'source': 'tradingeconomics',
                'category': event.get('Category', ''),
                'country': event.get('Country', country),
            }
            
            events.append(event_obj)
        
        df = pd.DataFrame(events)
        
        if not df.empty:
            df.sort_values('timestamp', inplace=True)
            df.reset_index(drop=True, inplace=True)
            
            # Count polarities
            bullish = (df['polarity'] == 'bullish').sum()
            bearish = (df['polarity'] == 'bearish').sum()
            neutral = (df['polarity'] == 'neutral').sum()
            
            print(f"[TRADING ECONOMICS] ✓ Retrieved {len(df)} events")
            print(f"[TRADING ECONOMICS]   Bullish: {bullish}, Bearish: {bearish}, Neutral: {neutral}")
            
            # Show sample
            print(f"[TRADING ECONOMICS] Sample events:")
            for _, row in df.head(5).iterrows():
                surprise = ""
                if row['forecast'] is not None and row['value'] is not None:
                    surprise = f" (Forecast: {row['forecast']}, Beat!" if row['polarity'] == 'bullish' else f" (Forecast: {row['forecast']}, Miss!"
                print(f"[TRADING ECONOMICS]   {row['timestamp'].date()}: {row['event_name']}{surprise}")
        
        return df
    
    def _map_event_type(self, category: str) -> str:
        """
        Map Trading Economics categories to standardized event types.
        """
        
        category_lower = category.lower()
        
        # Inflation
        if 'cpi' in category_lower or 'inflation' in category_lower:
            return 'CPI'
        elif 'pce' in category_lower:
            return 'PCE'
        
        # Employment
        elif 'non farm' in category_lower or 'payroll' in category_lower:
            return 'NFP'
        elif 'unemployment' in category_lower:
            return 'UNEMPLOYMENT'
        
        # GDP
        elif 'gdp' in category_lower:
            return 'GDP'
        
        # Fed / Interest Rates
        elif 'interest rate' in category_lower or 'fed funds' in category_lower:
            return 'FOMC'
        
        # PMI
        elif 'pmi' in category_lower or 'ism' in category_lower or 'purchasing' in category_lower:
            return 'PMI'
        
        # Retail
        elif 'retail' in category_lower:
            return 'RETAIL_SALES'
        
        # Consumer Sentiment
        elif 'confidence' in category_lower or 'sentiment' in category_lower:
            return 'CONSUMER_SENTIMENT'
        
        # Housing
        elif 'housing' in category_lower:
            return 'HOUSING'
        
        # Jobless Claims
        elif 'jobless' in category_lower or 'claims' in category_lower:
            return 'JOBLESS_CLAIMS'
        
        else:
            return 'OTHER'
    
    def _calculate_polarity(self, event: Dict) -> str:
        """
        Calculate polarity based on actual vs forecast.
        
        THIS IS THE MAGIC - detecting market surprises!
        
        Bullish = Actual beats forecast in a good way
        Bearish = Actual misses forecast or beats in a bad way
        Neutral = In line with forecast or no forecast
        """
        
        actual = event.get('Actual')
        forecast = event.get('Forecast')
        category = event.get('Category', '').lower()
        
        # No forecast = can't determine surprise
        if actual is None or forecast is None:
            return 'neutral'
        
        try:
            actual = float(actual)
            forecast = float(forecast)
        except (ValueError, TypeError):
            return 'neutral'
        
        # Calculate the surprise
        surprise = actual - forecast
        
        # Inflation (CPI, PCE, etc.): Lower than forecast = bullish
        if any(x in category for x in ['cpi', 'inflation', 'pce', 'price']):
            if abs(surprise) < 0.05:  # Within 0.05 is in-line
                return 'neutral'
            return 'bullish' if surprise < 0 else 'bearish'
        
        # Unemployment: Lower than forecast = bullish
        elif 'unemployment' in category or 'jobless' in category:
            if abs(surprise) < 0.05:
                return 'neutral'
            return 'bullish' if surprise < 0 else 'bearish'
        
        # Interest Rates: Lower than forecast = bullish (easier policy)
        elif 'interest rate' in category or 'fed funds' in category:
            if abs(surprise) < 0.05:
                return 'neutral'
            return 'bullish' if surprise < 0 else 'bearish'
        
        # Growth indicators (GDP, NFP, Retail, PMI, Confidence): Higher than forecast = bullish
        elif any(x in category for x in ['gdp', 'payroll', 'retail', 'pmi', 'confidence', 'sentiment', 'ism']):
            # Different thresholds for different indicators
            threshold = 0.1 if 'gdp' in category else 10 if 'payroll' in category else 1
            if abs(surprise) < threshold:
                return 'neutral'
            return 'bullish' if surprise > 0 else 'bearish'
        
        else:
            return 'neutral'


# Example usage and testing
if __name__ == '__main__':
    # Test the client
    client = TradingEconomicsClient()
    
    # Get events for your backtest period
    start = datetime(2025, 9, 13)
    end = datetime(2025, 12, 12)
    
    events = client.get_calendar_events(start, end)
    
    print(f"\n{'='*70}")
    print("DETAILED EVENT BREAKDOWN")
    print('='*70)
    
    if not events.empty:
        # Show all events with forecast/actual/previous
        for _, event in events.iterrows():
            print(f"\n{event['timestamp'].strftime('%Y-%m-%d %H:%M')} - {event['event_name']}")
            print(f"  Type: {event['event_type']}")
            print(f"  Forecast: {event['forecast']}")
            print(f"  Actual: {event['value']}")
            print(f"  Previous: {event['previous']}")
            print(f"  Polarity: {event['polarity'].upper()}")
            print(f"  Impact: {event['impact']}")
            
            # Show the surprise
            if event['forecast'] is not None and event['value'] is not None:
                surprise = event['value'] - event['forecast']
                surprise_pct = (surprise / event['forecast'] * 100) if event['forecast'] != 0 else 0
                print(f"  Surprise: {surprise:+.2f} ({surprise_pct:+.1f}%)")
    
    print(f"\n{'='*70}")
    print("SAVE THIS DATA")
    print('='*70)
    print("\nTo save: events.to_csv('trading_economics_events.csv', index=False)")