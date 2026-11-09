from __future__ import annotations
import os
from dataclasses import dataclass
from datetime import datetime
from typing import List
import pandas as pd
import requests
from textblob import TextBlob

@dataclass
class NewsConfig:
    use_finnhub: bool = False

def _sentiment_textblob(text: str) -> float:
    try:
        return float(TextBlob(text).sentiment.polarity)
    except Exception:
        return 0.0

def _sentiment_keywords(text: str) -> float:
    t = (text or "").lower()
    pos = ['surge','soar','rally','breakout','record','beat','upgrade','bullish','growth','profit']
    neg = ['plunge','crash','collapse','tumble','tank','miss','downgrade','bearish','lawsuit','investigation']
    pc = sum(1 for w in pos if w in t)
    nc = sum(1 for w in neg if w in t)
    tot = pc + nc
    return 0.0 if tot == 0 else (pc - nc) / tot

def score_headline(text: str) -> float:
    tb = _sentiment_textblob(text)
    kw = _sentiment_keywords(text)
    return max(-1.0, min(1.0, 0.7 * tb + 0.3 * kw))

def fetch_news(tickers: List[str], *, start: datetime, end: datetime, cfg: NewsConfig) -> pd.DataFrame:
    """
    Production news fetching with triple redundancy.
    Uses: Yahoo Finance → Finnhub → NewsAPI
    """
    try:
        from .production_news import fetch_news as production_fetch_news
        return production_fetch_news(tickers, start, end)
    except ImportError:
        # Fallback: return empty DataFrame if production_news not available
        print("[WARNING] production_news module not available, returning empty news DataFrame")
        return pd.DataFrame(columns=['ticker', 'timestamp', 'headline', 'sentiment', 'relevance'])
