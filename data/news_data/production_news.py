"""
Production News Aggregator
Triple-redundant: Yahoo Finance → Finnhub → NewsAPI

All sources complement each other:
- Yahoo: Free, reliable, good coverage
- Finnhub: Pre-calculated sentiment, good for historical
- NewsAPI: Broad coverage, paid tier for historical

100% API-driven, deployment-ready.
"""

import os
import pandas as pd
import yfinance as yf
import requests
import pytz
from datetime import datetime
from typing import List, Optional

class ProductionNewsAggregator:
    """
    Production-grade news aggregator with triple redundancy.
    No toys, only live APIs.
    """
    
    def __init__(self):
        self.yahoo_available = True  # Always available
        
        self.finnhub_key = os.getenv('FINNHUB_API_KEY')
        self.finnhub_available = bool(self.finnhub_key)
        
        self.newsapi_key = os.getenv('NEWSAPI_KEY')
        self.newsapi_available = bool(self.newsapi_key)
        
        # ✨ NEW: Alpha Vantage for historical news (FREE!)
        self.alphavantage_key = os.getenv('ALPHA_VANTAGE_KEY')
        self.alphavantage_available = bool(self.alphavantage_key)
        
        print(f"[NEWS] Sources available:")
        print(f"[NEWS]   ✓ Yahoo Finance (free)")
        if self.finnhub_available:
            print(f"[NEWS]   ✓ Finnhub (last 7 days)")
        if self.newsapi_available:
            print(f"[NEWS]   ✓ NewsAPI (last 30 days)")
        if self.alphavantage_available:
            print(f"[NEWS]   ✓ Alpha Vantage (historical)")
        
        if not self.finnhub_available and not self.newsapi_available:
            print(f"[NEWS]   ℹ️  Add FINNHUB_API_KEY or NEWSAPI_KEY for more sources")
        if not self.alphavantage_available:
            print(f"[NEWS]   ℹ️  Add ALPHA_VANTAGE_KEY for historical news (free from alphavantage.co)")
    
    def fetch_news(
        self,
        tickers: List[str],
        start_date: datetime,
        end_date: datetime
    ) -> pd.DataFrame:
        """
        ✨ SMART FETCH: Uses different sources for different time periods
        to maximize coverage beyond free API limits!
        
        Returns deduplicated, sentiment-analyzed news DataFrame.
        """
        from datetime import timedelta
        
        # Ensure timezone-aware dates
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=pytz.UTC)
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=pytz.UTC)
        
        days_requested = (end_date - start_date).days
        
        print(f"\n[NEWS] Fetching news from {start_date.date()} to {end_date.date()}")
        print(f"[NEWS] Monitoring {len(tickers)} tickers ({days_requested} days)")
        
        all_news = []
        
        # ============================================================
        # ✨ SMART STRATEGY: Split date range for maximum coverage
        # ============================================================
        
        # LAYER 1: Historical (30+ days ago) - Use Alpha Vantage
        if days_requested > 30 and self.alphavantage_available:
            historical_start = start_date
            historical_end = end_date - timedelta(days=30)
            
            print(f"[NEWS] Fetching historical news ({historical_start.date()} to {historical_end.date()})...")
            try:
                historical_news = self._fetch_alpha_vantage(tickers, historical_start, historical_end)
                if not historical_news.empty:
                    all_news.append(historical_news)
                    print(f"[NEWS] ✓ Alpha Vantage (historical): {len(historical_news)} articles")
            except Exception as e:
                print(f"[NEWS] Alpha Vantage failed: {e}")
        
        elif days_requested > 30 and not self.alphavantage_available:
            print(f"[NEWS] ⚠️  Backtest > 30 days, but no historical news source!")
            print(f"[NEWS]    Add ALPHA_VANTAGE_KEY (free) for full coverage")
            print(f"[NEWS]    Get it at: https://www.alphavantage.co/support/#api-key")
        
        # LAYER 2: Medium-term (8-30 days ago) - Use NewsAPI or Yahoo
        if days_requested > 7:
            mid_start = max(start_date, end_date - timedelta(days=30))
            mid_end = end_date - timedelta(days=7)
            
            if self.newsapi_available:
                print(f"[NEWS] Fetching mid-range news ({mid_start.date()} to {mid_end.date()})...")
                try:
                    mid_news = self._fetch_newsapi(tickers, mid_start, mid_end)
                    if not mid_news.empty:
                        all_news.append(mid_news)
                        print(f"[NEWS] ✓ NewsAPI (8-30 days): {len(mid_news)} articles")
                except Exception as e:
                    print(f"[NEWS] NewsAPI failed: {e}")
            else:
                # Fallback to Yahoo for this range
                print(f"[NEWS] Fetching mid-range news from Yahoo ({mid_start.date()} to {mid_end.date()})...")
                try:
                    yahoo_mid = self._fetch_yahoo(tickers, mid_start, mid_end)
                    if not yahoo_mid.empty:
                        all_news.append(yahoo_mid)
                        print(f"[NEWS] ✓ Yahoo (8-30 days): {len(yahoo_mid)} articles")
                except Exception as e:
                    print(f"[NEWS] Yahoo mid-range failed: {e}")
        
        # LAYER 3: Recent (last 7 days) - Use Finnhub (best sentiment quality)
        recent_start = end_date - timedelta(days=7)
        recent_end = end_date
        
        if self.finnhub_available:
            print(f"[NEWS] Fetching recent news ({recent_start.date()} to {recent_end.date()})...")
            try:
                recent_news = self._fetch_finnhub(tickers, recent_start, recent_end)
                if not recent_news.empty:
                    all_news.append(recent_news)
                    print(f"[NEWS] ✓ Finnhub (last 7 days): {len(recent_news)} articles")
            except Exception as e:
                print(f"[NEWS] Finnhub failed: {e}")
        else:
            # Fallback to Yahoo for recent news
            print(f"[NEWS] Fetching recent news from Yahoo ({recent_start.date()} to {recent_end.date()})...")
            try:
                yahoo_recent = self._fetch_yahoo(tickers, recent_start, recent_end)
                if not yahoo_recent.empty:
                    all_news.append(yahoo_recent)
                    print(f"[NEWS] ✓ Yahoo (last 7 days): {len(yahoo_recent)} articles")
            except Exception as e:
                print(f"[NEWS] Yahoo recent failed: {e}")
        
        # ============================================================
        # MERGE, DEDUPLICATE, AND ANALYZE
        # ============================================================
        
        if not all_news:
            print("[NEWS] ⚠️  No news from any source!")
            return pd.DataFrame(columns=[
                'timestamp', 'ticker', 'headline', 'description', 
                'source', 'url', 'polarity'
            ])
        
        # Combine all sources
        combined = pd.concat(all_news, ignore_index=True)
        
        # Deduplicate by headline + ticker (same article from different sources)
        combined = combined.drop_duplicates(subset=['headline', 'ticker'], keep='first')
        
        # Apply sentiment analysis to articles that don't have it
        combined = self._analyze_sentiment(combined)
        
        # Sort by timestamp
        combined = combined.sort_values('timestamp').reset_index(drop=True)
        
        # Summary with coverage report
        print(f"\n[NEWS] ✓ Total: {len(combined)} unique articles (after dedup)")
        print(f"[NEWS]   Date range: {combined['timestamp'].min()} → {combined['timestamp'].max()}")
        print(f"[NEWS]   Tickers with news: {', '.join(combined['ticker'].unique()[:10])}")
        
        # ✨ NEW: Coverage analysis
        actual_days = (combined['timestamp'].max() - combined['timestamp'].min()).days
        coverage_pct = (actual_days / days_requested * 100) if days_requested > 0 else 100
        
        # Show coverage status
        print(f"[NEWS] {'✓' if coverage_pct >= 50 else '⚠️ '} Coverage: {actual_days}/{days_requested} days ({coverage_pct:.0f}%)")
        
        # Provide helpful context based on what's available
        if coverage_pct < 50:
            if not self.alphavantage_available:
                print(f"[NEWS]    💡 Add ALPHA_VANTAGE_KEY for better historical coverage")
                print(f"[NEWS]       Get free key: https://www.alphavantage.co/support/#api-key")
            else:
                print(f"[NEWS]    ℹ️  Limited coverage may be due to:")
                print(f"[NEWS]       • Free API tier limits (Finnhub: 7 days, NewsAPI: 30 days)")
                print(f"[NEWS]       • Sparse news for these tickers in earlier period")
                print(f"[NEWS]       • Alpha Vantage rate limiting (5 calls/min)")
        
        # Sentiment breakdown
        positive = (combined['polarity'] > 0.1).sum()
        negative = (combined['polarity'] < -0.1).sum()
        neutral = len(combined) - positive - negative
        print(f"[NEWS]   Sentiment: {positive} positive, {negative} negative, {neutral} neutral")
        
        # Source breakdown
        sources = combined['source'].value_counts()
        print(f"[NEWS]   Sources: {dict(sources)}")
        
        return combined
    
    def _fetch_yahoo(
        self,
        tickers: List[str],
        start_date: datetime,
        end_date: datetime
    ) -> pd.DataFrame:
        """Fetch news from Yahoo Finance (always free)"""
        
        articles = []
        
        for ticker in tickers:
            try:
                stock = yf.Ticker(ticker)
                news = stock.news
                
                if not news:
                    continue
                
                for article in news:
                    try:
                        ts = article.get('providerPublishTime')
                        if not ts:
                            continue
                        
                        pub_time = datetime.fromtimestamp(ts, tz=pytz.UTC)
                        
                        # Filter by date range
                        if start_date <= pub_time <= end_date:
                            articles.append({
                                'timestamp': pub_time,
                                'ticker': ticker,
                                'headline': article.get('title', ''),
                                'description': article.get('summary', ''),
                                'source': f"yahoo_{article.get('publisher', 'finance')}",
                                'url': article.get('link', ''),
                                'polarity': 0.0  # Will be calculated
                            })
                    except Exception:
                        continue
                        
            except Exception as e:
                continue
        
        return pd.DataFrame(articles)
    
    def _fetch_finnhub(
        self,
        tickers: List[str],
        start_date: datetime,
        end_date: datetime
    ) -> pd.DataFrame:
        """Fetch news from Finnhub with pre-calculated sentiment"""
        
        articles = []
        
        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')
        
        for ticker in tickers:
            try:
                url = "https://finnhub.io/api/v1/company-news"
                params = {
                    'symbol': ticker,
                    'from': start_str,
                    'to': end_str,
                    'token': self.finnhub_key
                }
                
                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()
                
                data = response.json()
                
                for article in data:
                    pub_time = datetime.fromtimestamp(article['datetime'], tz=pytz.UTC)
                    
                    articles.append({
                        'timestamp': pub_time,
                        'ticker': ticker,
                        'headline': article.get('headline', ''),
                        'description': article.get('summary', ''),
                        'source': f"finnhub_{article.get('source', '')}",
                        'url': article.get('url', ''),
                        'polarity': article.get('sentiment', 0.0)  # Finnhub provides this!
                    })
                
                # Rate limiting (60/min = 1 per second)
                import time
                time.sleep(1.1)
                
            except Exception as e:
                continue
        
        return pd.DataFrame(articles)
    
    def _fetch_newsapi(
        self,
        tickers: List[str],
        start_date: datetime,
        end_date: datetime
    ) -> pd.DataFrame:
        """Fetch news from NewsAPI (paid tier recommended for historical)"""
        
        # Build query for stock-related news
        ticker_query = ' OR '.join(tickers[:20])  # Limit to avoid too long URLs
        query = f"({ticker_query}) AND (stock OR market OR earnings OR trading)"
        
        url = "https://newsapi.org/v2/everything"
        params = {
            'q': query,
            'from': start_date.strftime('%Y-%m-%d'),
            'to': end_date.strftime('%Y-%m-%d'),
            'language': 'en',
            'sortBy': 'publishedAt',
            'apiKey': self.newsapi_key,
            'pageSize': 100
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('status') != 'ok':
                return pd.DataFrame()
            
            articles = []
            
            for article in data.get('articles', []):
                pub_time = pd.to_datetime(article['publishedAt'], utc=True)
                
                # Match article to ticker (handle None values)
                title = (article.get('title') or '').upper()
                description = (article.get('description') or '').upper()
                matched_ticker = None
                
                for ticker in tickers:
                    if ticker.upper() in title or ticker.upper() in description:
                        matched_ticker = ticker
                        break
                
                if matched_ticker:
                    articles.append({
                        'timestamp': pub_time,
                        'ticker': matched_ticker,
                        'headline': article.get('title') or '',
                        'description': article.get('description') or '',
                        'source': f"newsapi_{article.get('source', {}).get('name', '')}",
                        'url': article.get('url') or '',
                        'polarity': 0.0  # Will be calculated
                    })
            
            return pd.DataFrame(articles)
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 426:
                print("[NEWS] NewsAPI: Upgrade required for this date range")
            raise
    
    def _fetch_alpha_vantage(
        self,
        tickers: List[str],
        start_date: datetime,
        end_date: datetime
    ) -> pd.DataFrame:
        """
        Fetch news from Alpha Vantage (FREE historical news!)
        Great for backtests > 30 days
        """
        
        articles = []
        
        # Alpha Vantage uses YYYYMMDDTHHMM format
        start_str = start_date.strftime('%Y%m%dT%H%M')
        end_str = end_date.strftime('%Y%m%dT%H%M')
        
        for ticker in tickers:
            try:
                url = "https://www.alphavantage.co/query"
                params = {
                    'function': 'NEWS_SENTIMENT',
                    'tickers': ticker,
                    'time_from': start_str,
                    'time_to': end_str,
                    'limit': 1000,  # Max results
                    'apikey': self.alphavantage_key
                }
                
                response = requests.get(url, params=params, timeout=15)
                response.raise_for_status()
                
                data = response.json()
                
                # Check for API errors
                if 'Error Message' in data or 'Note' in data:
                    continue
                
                for item in data.get('feed', []):
                    try:
                        # Parse timestamp: "20231215T120000"
                        pub_time = datetime.strptime(item['time_published'], '%Y%m%dT%H%M%S')
                        pub_time = pub_time.replace(tzinfo=pytz.UTC)
                        
                        # Alpha Vantage provides sentiment score!
                        sentiment_score = float(item.get('overall_sentiment_score', 0.0))
                        
                        articles.append({
                            'timestamp': pub_time,
                            'ticker': ticker,
                            'headline': item.get('title', ''),
                            'description': item.get('summary', ''),
                            'source': f"alphavantage_{item.get('source', '')}",
                            'url': item.get('url', ''),
                            'polarity': sentiment_score  # Already calculated!
                        })
                    except Exception:
                        continue
                
                # Alpha Vantage rate limit: 5 calls/min on free tier
                import time
                time.sleep(12)  # Wait 12 seconds between calls
                
            except Exception as e:
                continue
        
        return pd.DataFrame(articles)
    
    def _analyze_sentiment(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Analyze sentiment for articles that don't have it.
        Uses TextBlob + enhanced keywords.
        """
        
        # Try to import TextBlob
        try:
            from textblob import TextBlob
            use_textblob = True
        except ImportError:
            use_textblob = False
            print("[NEWS] TextBlob not available, using keyword-only analysis")
        
        # Enhanced keyword lists
        positive_keywords = {
            'surge', 'soar', 'rally', 'breakout', 'record', 'beat', 'beats',
            'exceed', 'exceeds', 'outperform', 'gain', 'gains', 'rise', 'rises',
            'jump', 'jumps', 'climb', 'strong', 'growth', 'profit', 'profits',
            'upgrade', 'upgraded', 'buy', 'bullish', 'boost', 'advance',
            'optimistic', 'success', 'winner', 'winning', 'best', 'top', 'leading'
        }
        
        negative_keywords = {
            'plunge', 'plunges', 'crash', 'crashes', 'collapse', 'tumble', 'tank',
            'slump', 'fall', 'falls', 'drop', 'drops', 'decline', 'weak', 'loss',
            'losses', 'miss', 'misses', 'disappoint', 'underperform', 'downgrade',
            'sell', 'bearish', 'cut', 'concern', 'worry', 'fear', 'risk',
            'lawsuit', 'investigation', 'fraud', 'scandal', 'probe'
        }
        
        def calculate_sentiment(text):
            """Calculate sentiment score"""
            if not text or pd.isna(text):
                return 0.0
            
            text = str(text).lower()
            
            # TextBlob component (if available)
            tb_score = 0.0
            if use_textblob:
                try:
                    blob = TextBlob(text)
                    tb_score = blob.sentiment.polarity
                except:
                    pass
            
            # Keyword component
            pos_count = sum(1 for word in positive_keywords if word in text)
            neg_count = sum(1 for word in negative_keywords if word in text)
            
            total = pos_count + neg_count
            kw_score = 0.0 if total == 0 else (pos_count - neg_count) / total
            
            # Boost for strong indicators
            strong_positive = ['surge', 'soar', 'rally', 'record', 'beat', 'breakout']
            strong_negative = ['plunge', 'crash', 'collapse', 'tumble', 'tank']
            
            if any(word in text for word in strong_positive):
                kw_score = min(1.0, kw_score + 0.3)
            if any(word in text for word in strong_negative):
                kw_score = max(-1.0, kw_score - 0.3)
            
            # Weighted combination
            if use_textblob:
                final_score = 0.6 * tb_score + 0.4 * kw_score
            else:
                final_score = kw_score
            
            return max(-1.0, min(1.0, final_score))
        
        # Apply sentiment to articles that need it (polarity == 0)
        needs_sentiment = df['polarity'].abs() < 0.01
        
        if needs_sentiment.any():
            print(f"[NEWS] Analyzing sentiment for {needs_sentiment.sum()} articles...")
            
            # Use headline + description for better accuracy
            df.loc[needs_sentiment, 'polarity'] = df.loc[needs_sentiment].apply(
                lambda row: calculate_sentiment(
                    f"{row['headline']} {row.get('description', '')}"
                ),
                axis=1
            )
        
        return df


# Convenience function for integration
def fetch_news(
    tickers: List[str],
    start_date: datetime,
    end_date: datetime
) -> pd.DataFrame:
    """
    Convenience function to fetch news.
    Use this in your main backtest code.
    """
    aggregator = ProductionNewsAggregator()
    return aggregator.fetch_news(tickers, start_date, end_date)


if __name__ == '__main__':
    """Test the production news aggregator"""
    
    from datetime import timedelta
    
    tickers = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA']
    end = datetime.now()
    start = end - timedelta(days=7)
    
    print("=" * 70)
    print("TESTING PRODUCTION NEWS AGGREGATOR")
    print("=" * 70)
    
    news = fetch_news(tickers, start, end)
    
    if not news.empty:
        print("\n" + "=" * 70)
        print("SAMPLE HEADLINES")
        print("=" * 70)
        
        for _, article in news.head(10).iterrows():
            sentiment = "📈" if article['polarity'] > 0.1 else "📉" if article['polarity'] < -0.1 else "➡️"
            print(f"{sentiment} [{article['ticker']}] {article['headline'][:80]}")
            print(f"   Source: {article['source']}, Polarity: {article['polarity']:.3f}")
    else:
        print("\n⚠️  No news found!")
