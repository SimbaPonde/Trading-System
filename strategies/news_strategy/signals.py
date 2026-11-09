from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd
from .ai import AIRanker, AIConfig

@dataclass
class Signal:
    ticker: str
    time: pd.Timestamp
    side: str
    price: float
    category: str
    reason: str
    confidence: float
    stop_dist: float

def _trend_score(df: pd.DataFrame) -> float:
    close = df["Close"].astype(float)
    sma10 = close.rolling(10).mean()
    sma20 = close.rolling(20).mean()
    if sma20.isna().all() or sma10.isna().all():
        return 0.0
    return float(np.tanh((sma10.iloc[-1] - sma20.iloc[-1]) / (close.iloc[-1] + 1e-9) * 10.0))

def _atr(df: pd.DataFrame, n: int = 14) -> float:
    h = df["High"].astype(float)
    l = df["Low"].astype(float)
    c = df["Close"].astype(float)
    tr = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    v = tr.rolling(n).mean().iloc[-1]
    return float(v) if pd.notna(v) else float(tr.mean())

def _news_features(news_ticker: pd.DataFrame) -> Tuple[float, int]:
    if news_ticker is None or news_ticker.empty:
        return 0.0, 0
    pol = float(np.clip(news_ticker["polarity"].astype(float).mean(), -1, 1))
    return pol, int(len(news_ticker))

def _macro_alignment(macros: pd.DataFrame) -> float:
    if macros is None or macros.empty:
        return 0.0
    recent = macros.tail(3)
    score = 0.0
    for _, r in recent.iterrows():
        p = str(r.get("polarity","neutral")).lower()
        if p == "bullish":
            score += 1.0
        elif p == "bearish":
            score -= 1.0
    return float(np.clip(score / max(len(recent), 1), -1, 1))

def generate_signals(
    *,
    prices: Dict[str, pd.DataFrame],
    news: pd.DataFrame,
    macros: pd.DataFrame,
    etfs: List[str],
    sentiment_threshold: float,
    min_articles: int,
    ai_enabled: bool = True
) -> List[Signal]:
    ai = AIRanker(AIConfig(enabled=ai_enabled))
    out: List[Signal] = []

    news_by = {t: df for t, df in news.groupby("ticker")} if news is not None and not news.empty else {}
    macro_score = _macro_alignment(macros)

    for ticker, df in prices.items():
        if df is None or df.empty:
            continue

        df = df.copy()
        df.index = pd.to_datetime(df.index)
        last_ts = pd.to_datetime(df.index[-1], utc=True) if df.index.tz is None else df.index[-1]
        last_close = float(df["Close"].iloc[-1])
        trend = _trend_score(df)
        atr = _atr(df)
        stop_dist = max(atr, 0.01 * last_close)

        # NEWS-only: single-name equities only AND must have ticker news
        if ticker not in etfs:
            nt = news_by.get(ticker, pd.DataFrame())
            sent, n_articles = _news_features(nt)
            if n_articles < min_articles:
                continue
            if abs(sent) < sentiment_threshold:
                continue

            side = "BUY" if sent > 0 else "SELL"
            conf = ai.score(sentiment=sent, macro_alignment=0.0, trend=trend)
            out.append(Signal(
                ticker=ticker,
                time=last_ts,
                side=side,
                price=last_close,
                category="News",
                reason=f"NEWS(sent={sent:.2f}, n={n_articles}) trend={trend:.2f}",
                confidence=conf,
                stop_dist=stop_dist
            ))
            continue

        # MACRO trades: ETFs only
        if ticker in etfs and macros is not None and not macros.empty:
            if macro_score == 0.0:
                continue
            side = "BUY" if macro_score > 0 else "SELL"
            conf = ai.score(sentiment=0.0, macro_alignment=macro_score, trend=trend)
            out.append(Signal(
                ticker=ticker,
                time=last_ts,
                side=side,
                price=last_close,
                category="Macro",
                reason=f"MACRO(score={macro_score:.2f}) trend={trend:.2f}",
                confidence=conf,
                stop_dist=stop_dist
            ))

    # Confluence upgrade
    if macros is not None and not macros.empty and macro_score != 0.0:
        for i, s in enumerate(out):
            if s.category == "News":
                if (macro_score > 0 and s.side == "BUY") or (macro_score < 0 and s.side == "SELL"):
                    out[i] = Signal(**{**s.__dict__, "category": "Confluence", "reason": s.reason + f" + MACRO({macro_score:.2f})"})
    return out
