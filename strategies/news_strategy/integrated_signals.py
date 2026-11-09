"""
strategy/integrated_news_macro.py - NEWS & MACRO ONLY VERSION (ETF FIXED)

CRITICAL FIXES:
1. Macro signals → ETFs ONLY
2. News signals → ALL tickers (stocks & ETFs)
3. WIDER time windows for FRED daily data (24-48 hours vs 2 hours)
4. Proper ETF detection
5. Enhanced categorization

ETF MACRO STRATEGY:
- SPY, QQQ, IWM, DIA = Macro-trading ETFs
- Stocks = News-driven only
- Confluence = Both news + macro alignment
"""

import pandas as pd
import numpy as np
from datetime import timedelta


# ============================================================================
# ETF CONFIGURATION - Define which tickers get macro signals
# ============================================================================

# ETFs that trade on macro events
MACRO_ETFS = {
    'SPY',   # S&P 500 - broad market
    'QQQ',   # Nasdaq 100 - tech heavy
    'IWM',   # Russell 2000 - small caps
    'DIA',   # Dow Jones - blue chips
    'XLF',   # Financials - rate sensitive
    'XLE',   # Energy - inflation sensitive
    'XLK',   # Technology
    'XLV',   # Healthcare
    'XLI',   # Industrials
    'TLT',   # Long-term Treasury
    'GLD',   # Gold
}

def is_macro_etf(ticker):
    """Check if ticker is a macro-trading ETF."""
    return ticker.upper() in MACRO_ETFS


# ============================================================================
# MACRO EVENT DETECTION
# ============================================================================

TIER_1_EVENTS = [
    'fomc', 'interest rate', 'fed funds', 'federal reserve decision',
    'cpi', 'consumer price index', 'inflation',
    'non-farm payroll', 'nfp', 'payroll', 'jobs report',
    'gdp', 'gross domestic product',
    'unemployment rate',
    # Add FRED event types
    'pce', 'pce price index',
    'effective fed funds rate',
]

TIER_2_EVENTS = [
    'retail sales',
    'ppi', 'producer price index',
    'consumer confidence', 'consumer sentiment',
    'pmi', 'manufacturing pmi', 'services pmi',
    'jobless claims', 'unemployment claims', 'initial jobless claims',
    'industrial production',
    'housing starts',
]

DIRECTIONAL_KEYWORDS = {
    'bullish': [
        'rate cut', 'dovish', 'easing', 'cut rates',
        'better than expected', 'beat expectations', 'beats forecast',
        'strong growth', 'job growth', 'robust',
    ],
    'bearish': [
        'rate hike', 'hawkish', 'tightening', 'raise rates',
        'worse than expected', 'miss expectations', 'misses forecast',
        'weak growth', 'job losses', 'layoffs', 'contraction',
    ]
}


def get_etf_targets_for_macro(macro_event):
    """Determine which ETFs to trade based on macro event type."""
    event_type = macro_event.get('event_type', '').upper()
    
    if any(word in event_type for word in ['FOMC', 'INTEREST', 'FED_FUNDS', 'FEDFUNDS']):
        return ['SPY', 'QQQ', 'XLF']
    elif 'CPI' in event_type or 'INFLATION' in event_type or 'PCE' in event_type:
        return ['SPY', 'QQQ']
    elif any(word in event_type for word in ['PAYROLL', 'NFP', 'UNEMPLOYMENT', 'JOBLESS']):
        return ['SPY', 'IWM']
    elif 'GDP' in event_type:
        return ['SPY', 'QQQ', 'IWM']
    else:
        return ['SPY']


def get_macro_event_impact(t, macro_df, ticker=None, is_etf=False):
    """
    Detect high-impact macro events with WIDER windows for FRED daily data.
    
    CRITICAL FIX: FRED data is DAILY (no specific time), so use 24-48 hour windows
    instead of 2-hour windows.
    
    ETFs get wider windows (24-48 hours) since macro affects market broadly.
    Stocks get narrower windows (4-8 hours) for confluence only.
    """
    if macro_df is None or macro_df.empty:
        return None
    
    # CRITICAL: Use WIDER windows for FRED daily data
    if is_etf:
        # ETFs: Match macro events within ±24 hours (FRED releases are daily)
        window_hours_tier1 = 24  # Was 2, now 24 for daily FRED data
        window_hours_tier2 = 48  # Was 4, now 48 for daily FRED data
    else:
        # Stocks: Narrower window for confluence detection
        window_hours_tier1 = 8
        window_hours_tier2 = 12
    
    time_col = None
    for col in ['time', 'timestamp', 'datetime', 'date', 'published_at']:
        if col in macro_df.columns:
            time_col = col
            break
    
    if not time_col:
        return None
    
    try:
        macro_df = macro_df.copy()
        macro_df[time_col] = pd.to_datetime(macro_df[time_col], utc=True)
        
        if not hasattr(t, 'tz') or t.tz is None:
            t = pd.Timestamp(t, tz='UTC')
        else:
            t = t.tz_convert('UTC') if t.tz is not None else pd.Timestamp(t, tz='UTC')
        
        # Try Tier 1 events first (wider window)
        window_start = t - timedelta(hours=window_hours_tier1)
        window_end = t + timedelta(hours=window_hours_tier1)
        
        mask = (macro_df[time_col] >= window_start) & (macro_df[time_col] <= window_end)
        matches = macro_df[mask]
        
        if not matches.empty:
            for _, row in matches.iterrows():
                if row.get('polarity') == 'neutral':
                    continue
                event_result = parse_macro_event(row, tier=1)
                if event_result:
                    return event_result
        
        # Try Tier 2 events (even wider window)
        window_start = t - timedelta(hours=window_hours_tier2)
        window_end = t + timedelta(hours=window_hours_tier2)
        
        mask = (macro_df[time_col] >= window_start) & (macro_df[time_col] <= window_end)
        matches = macro_df[mask]
        
        if not matches.empty:
            for _, row in matches.iterrows():
                if row.get('polarity') == 'neutral':
                    continue
                event_result = parse_macro_event(row, tier=2)
                if event_result:
                    return event_result
        
        return None
        
    except Exception as e:
        print(f"[MACRO DEBUG] Error in get_macro_event_impact: {e}")
        return None


def parse_macro_event(row, tier):
    """
    Parse a single macro event row and determine type/direction.
    Enhanced to handle FRED data format.
    """
    # Get event text from multiple possible columns
    event_name = str(row.get('event', row.get('event_name', row.get('event_type', '')))).lower()
    event_desc = str(row.get('description', '')).lower()
    event_text = event_name + ' ' + event_desc
    
    # Determine event type
    event_type = None
    tier_matched = tier
    
    event_keywords = TIER_1_EVENTS if tier == 1 else TIER_2_EVENTS
    
    for keyword in event_keywords:
        if keyword in event_text:
            event_type = keyword.upper().replace(' ', '_')
            break
    
    if not event_type:
        return None
    
    # Determine direction
    direction = None
    
    # Method 1: Keywords
    for keyword in DIRECTIONAL_KEYWORDS['bullish']:
        if keyword in event_text:
            direction = 'bullish'
            break
    
    if not direction:
        for keyword in DIRECTIONAL_KEYWORDS['bearish']:
            if keyword in event_text:
                direction = 'bearish'
                break
    
    # Method 2: Actual vs Expected/Forecast
    if not direction:
        for val_col in ['actual', 'value']:
            for fcast_col in ['forecast', 'expected', 'previous']:
                if val_col in row and fcast_col in row:
                    try:
                        actual = float(row[val_col])
                        forecast = float(row[fcast_col])
                        surprise = actual - forecast
                        
                        # Determine direction based on event type
                        if any(word in event_type for word in ['CPI', 'PPI', 'INFLATION', 'PCE']):
                            direction = 'bearish' if surprise > 0 else 'bullish'
                        elif any(word in event_type for word in ['GDP', 'PAYROLL', 'RETAIL', 'JOB', 'NFP']):
                            direction = 'bullish' if surprise > 0 else 'bearish'
                        elif any(word in event_type for word in ['UNEMPLOYMENT', 'JOBLESS']):
                            direction = 'bearish' if surprise > 0 else 'bullish'
                        elif any(word in event_type for word in ['RATE', 'FOMC', 'FED']):
                            direction = 'bearish' if surprise > 0 else 'bullish'
                        
                        if direction:
                            break
                    except (ValueError, TypeError):
                        pass
                if direction:
                    break
    
    # Method 3: Polarity fallback (for FRED data that might have polarity)
    if not direction and 'polarity' in row:
        try:
            pol = float(row.get('polarity', 0))
            if abs(pol) >= 0.02:
                direction = 'bullish' if pol > 0 else 'bearish'
        except (ValueError, TypeError):
            pass
    
    # Method 4: For FRED data, look at value changes
    if not direction and 'value' in row and 'previous' in row:
        try:
            current = float(row['value'])
            previous = float(row['previous'])
            change = current - previous
            
            # Assume positive change is bullish for most indicators
            if abs(change) > 0.01:  # Meaningful change
                direction = 'bullish' if change > 0 else 'bearish'
        except (ValueError, TypeError):
            pass
    
    if direction:
        # Get time column
        time_col = None
        for col in ['time', 'timestamp', 'datetime', 'event_time']:
            if col in row:
                time_col = col
                break
        
        return {
            'event_type': event_type,
            'tier': tier_matched,
            'direction': direction,
            'impact_score': 1.0 if tier_matched == 1 else 0.7,
            'event_name': event_name,
            'event_time': row.get(time_col) if time_col else None,
        }
    
    return None


def get_news_at_bar(t, news_df, ticker=None, interval='1d'):
    """
    CRITICAL FIX: Only get news that JUST APPEARED at this specific bar.
    Uses NARROW matching window based on interval.
    
    Returns: (sentiment, strength, polarity_score) or (None, None, None)
    """
    
    if news_df is None or news_df.empty:
        return None, None, None
    
    # CRITICAL: Use VERY narrow windows - only match news from current bar
    if interval in ['1d', 'daily']:
        window_minutes = 30  # ±30 minutes for daily bars
    elif interval in ['1h']:
        window_minutes = 15  # ±15 minutes for hourly bars
    elif interval in ['4h']:
        window_minutes = 30  # ±30 minutes for 4-hour bars
    else:
        window_minutes = 5   # ±5 minutes for intraday
    
    time_col = None
    for col in ['published_at', 'time', 'timestamp', 'datetime']:
        if col in news_df.columns:
            time_col = col
            break
    
    if not time_col:
        return None, None, None
    
    try:
        news_df = news_df.copy()
        news_df[time_col] = pd.to_datetime(news_df[time_col], utc=True)
        
        if not hasattr(t, 'tz') or t.tz is None:
            t = pd.Timestamp(t, tz='UTC')
        
        window_start = t - timedelta(minutes=window_minutes)
        window_end = t + timedelta(minutes=window_minutes)
        
        # Filter by ticker if provided
        if ticker and 'ticker' in news_df.columns:
            mask = (
                (news_df[time_col] >= window_start) &
                (news_df[time_col] <= window_end) &
                (news_df['ticker'].str.upper() == ticker.upper())
            )
        else:
            mask = (
                (news_df[time_col] >= window_start) &
                (news_df[time_col] <= window_end)
            )
        
        matches = news_df[mask]
        
        if matches.empty:
            return None, None, None
        
        # Get the strongest sentiment from news at this bar
        if 'polarity' in matches.columns:
            polarities = matches['polarity'].abs()
            strongest_idx = polarities.idxmax()
            polarity = float(matches.loc[strongest_idx, 'polarity'])
            
            # CRITICAL: Very high threshold to avoid spam
            if abs(polarity) >= 0.30:  # Was 0.20, now 0.30 for strictness
                sentiment = 'bullish' if polarity > 0 else 'bearish'
                strength = 'very_strong' if abs(polarity) >= 0.40 else 'strong'
                return sentiment, strength, polarity
        
        return None, None, None
    
    except Exception:
        return None, None, None


# ============================================================================
# COOLDOWN SYSTEM
# ============================================================================

class NewsEventCooldown:
    """Prevent signal spam by enforcing cooldown periods."""
    
    def __init__(self, cooldown_hours=6):
        self.cooldown_hours = cooldown_hours
        self.last_signals = {}  # {ticker: {sentiment: last_time}}
    
    def can_signal(self, ticker, sentiment, current_time):
        """Check if enough time has passed since last signal."""
        if ticker not in self.last_signals:
            self.last_signals[ticker] = {}
        
        if sentiment not in self.last_signals[ticker]:
            self.last_signals[ticker][sentiment] = current_time
            return True
        
        last_time = self.last_signals[ticker][sentiment]
        time_diff = current_time - last_time
        
        if time_diff >= timedelta(hours=self.cooldown_hours):
            self.last_signals[ticker][sentiment] = current_time
            return True
        
        return False
    
    def reset(self):
        """Clear all cooldowns."""
        self.last_signals.clear()


# ============================================================================
# MAIN SIGNAL GENERATION
# ============================================================================

def generate_integrated_signals(
    df: pd.DataFrame,
    news_df: pd.DataFrame = None,
    macro_df: pd.DataFrame = None,
    ticker: str = "",
    interval: str = "1d",
    is_etf: bool = False,
) -> list:
    """
    Generate signals based ONLY on FRESH news and macro events.
    
    CRITICAL FIXES:
    1. ETFs: Trade on macro events ONLY (TIER 1 events, 24-hour window)
    2. Stocks: Trade on very strong news ONLY
    3. Stocks: Enhance with TIER 2 macro confluence (12-hour window)
    4. Use cooldown to prevent spam
    5. Proper categorization (news_score, macro_score)
    
    Strategy:
    - ETFs (SPY, QQQ, IWM, DIA): Macro-driven (FRED events)
    - Stocks: News-driven with optional macro confluence
    """
    
    if df is None or df.empty:
        return []
    
    # Auto-detect if ETF if not explicitly set
    if not is_etf:
        is_etf = is_macro_etf(ticker)
    
    signals = []
    # FIX 3: Different cooldowns for macro vs news
    is_etf = ticker in ['SPY', 'QQQ', 'IWM', 'DIA']
    if is_etf:
        cooldown = NewsEventCooldown(cooldown_hours=168)  # 7 days for ETF macro
    else:
        cooldown = NewsEventCooldown(cooldown_hours=6)  # 6 hours for stocks/news
    
    # Add basic price columns if missing
    if 'Close' not in df.columns:
        return []
    
    # Calculate simple ATR for stop loss
    df = df.copy()
    high = df['High']
    low = df['Low']
    close = df['Close'].shift(1)
    
    tr1 = high - low
    tr2 = (high - close).abs()
    tr3 = (low - close).abs()
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(window=14, min_periods=1).mean()
    
    # Process each bar
    for i in range(len(df)):
        t = df.index[i]
        close = df['Close'].iloc[i]
        high = df['High'].iloc[i]
        low = df['Low'].iloc[i]
        atr = df['ATR'].iloc[i]
        
        if pd.isna(atr) or atr <= 0:
            continue
        
        # Check for macro event AT THIS BAR (WIDER window for ETFs)
        macro_event = get_macro_event_impact(t, macro_df, ticker=ticker, is_etf=is_etf)
        
        # ================================================================
        # ETF LOGIC: Trade on Macro Events ONLY
        # ================================================================
        
        if is_etf and macro_event:
            
            # ETFs trade on BOTH Tier 1 and Tier 2 macro events
            # (Tier 1 = High impact, Tier 2 = Medium impact)
            
            # Check cooldown
            if not cooldown.can_signal(ticker, macro_event['direction'], t):
                continue
            
            grade = 'AAA' if macro_event['tier'] == 1 else 'AA'
            confidence = 0.90 if macro_event['tier'] == 1 else 0.75
            
            if macro_event['direction'] == 'bullish':
                signals.append({
                    'time': t,
                    'type': 'BUY',
                    'side': 'BUY',
                    'reason': f"MACRO_{macro_event['event_type']}_BULLISH",
                    'original_reason': f"MACRO_{macro_event['event_type']}_BULLISH",
                    'grade': grade,
                    'ticker': ticker,
                    'price': close,
                    'atr': atr,
                    'stop_dist': 1.0 * atr,
                    'stop_loss': close - (1.0 * atr),
                    'profit_target': close + (2.5 * atr),
                    'time_exit_bars': 2,
                    'strength': 0.95,
                    'confidence': confidence,
                    'macro_event': macro_event['event_type'],
                    'macro_tier': macro_event['tier'],
                    'bar_index': i,
                    'news_score': 0.0,
                    'macro_score': 1.0 if macro_event['tier'] == 1 else 0.7,
                    'tech_score': 0.0,
                })
            
            elif macro_event['direction'] == 'bearish':
                signals.append({
                    'time': t,
                    'type': 'SELL',
                    'side': 'SELL',
                    'reason': f"MACRO_{macro_event['event_type']}_BEARISH",
                    'original_reason': f"MACRO_{macro_event['event_type']}_BEARISH",
                    'grade': grade,
                    'ticker': ticker,
                    'price': close,
                    'atr': atr,
                    'stop_dist': 1.0 * atr,
                    'stop_loss': close + (1.0 * atr),
                    'profit_target': close - (2.5 * atr),
                    'time_exit_bars': 2,
                    'strength': 0.95,
                    'confidence': confidence,
                    'macro_event': macro_event['event_type'],
                    'macro_tier': macro_event['tier'],
                    'bar_index': i,
                    'news_score': 0.0,
                    'macro_score': -1.0 if macro_event['tier'] == 1 else -0.7,
                    'tech_score': 0.0,
                })
        
        # ================================================================
        # STOCK LOGIC: Trade on FRESH Strong News ONLY
        # ================================================================
        
        if not is_etf:
            # Get news AT THIS BAR (narrow window)
            news_sent, news_strength, polarity = get_news_at_bar(t, news_df, ticker, interval)
            
            # Only trade on VERY STRONG news
            if news_strength == 'very_strong' and news_sent:
                
                # Check cooldown
                if not cooldown.can_signal(ticker, news_sent, t):
                    continue
                
                # Check for macro confluence (Tier 2 events)
                has_macro = (macro_event and macro_event['tier'] == 2 and 
                           macro_event['direction'] == news_sent)
                
                if news_sent == 'bullish':
                    signals.append({
                        'time': t,
                        'type': 'BUY',
                        'side': 'BUY',
                        'reason': 'VERY_STRONG_NEWS_BUY' + ('_MACRO2' if has_macro else ''),
                        'original_reason': 'VERY_STRONG_NEWS_BUY',
                        'grade': 'AAA' if has_macro else 'A',
                        'ticker': ticker,
                        'price': close,
                        'atr': atr,
                        'stop_dist': 1.5 * atr,
                        'stop_loss': close - (1.5 * atr),
                        'profit_target': close + (3.0 * atr),
                        'time_exit_bars': 3,
                        'strength': 0.90,
                        'confidence': 0.85,
                        'news_strength': news_strength,
                        'news_polarity': polarity,
                        'bar_index': i,
                        'news_score': 1.0,
                        'macro_score': 0.7 if has_macro else 0.0,
                        'tech_score': 0.0,
                    })
                
                elif news_sent == 'bearish':
                    signals.append({
                        'time': t,
                        'type': 'SELL',
                        'side': 'SELL',
                        'reason': 'VERY_STRONG_NEWS_SELL' + ('_MACRO2' if has_macro else ''),
                        'original_reason': 'VERY_STRONG_NEWS_SELL',
                        'grade': 'AAA' if has_macro else 'A',
                        'ticker': ticker,
                        'price': close,
                        'atr': atr,
                        'stop_dist': 1.5 * atr,
                        'stop_loss': close + (1.5 * atr),
                        'profit_target': close - (3.0 * atr),
                        'time_exit_bars': 3,
                        'strength': 0.90,
                        'confidence': 0.85,
                        'news_strength': news_strength,
                        'news_polarity': polarity,
                        'bar_index': i,
                        'news_score': -1.0,
                        'macro_score': -0.7 if has_macro else 0.0,
                        'tech_score': 0.0,
                    })
    
    return signals


def filter_by_grade(signals, min_grade='AA'):
    """Filter signals by quality grade."""
    grade_order = {'AAA': 3, 'AA': 2, 'A': 2, 'B': 1}
    min_level = grade_order.get(min_grade, 1)
    
    return [s for s in signals if grade_order.get(s.get('grade', 'B'), 0) >= min_level]