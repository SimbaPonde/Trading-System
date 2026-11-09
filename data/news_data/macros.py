from __future__ import annotations
import os
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
import pandas as pd
import requests

@dataclass
class MacroConfig:
    include_event_types: Optional[List[str]] = None
    redundant_sources: bool = True

CANON_COLS = ["timestamp","ticker","event_type","event_name","value","forecast","previous","polarity","impact","source"]

def _normalize_polarity(p: str) -> str:
    p = (p or "").lower().strip()
    if p in ("bullish","positive","up"):
        return "bullish"
    if p in ("bearish","negative","down"):
        return "bearish"
    return "neutral"

def _fetch_te_calendar(start: datetime, end: datetime) -> pd.DataFrame:
    key = os.environ.get("TRADING_ECONOMICS_KEY")
    if not key:
        return pd.DataFrame(columns=CANON_COLS)

    url = "https://api.tradingeconomics.com/calendar"
    params = {"d1": start.strftime("%Y-%m-%d"), "d2": end.strftime("%Y-%m-%d"), "c": key}
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return pd.DataFrame(columns=CANON_COLS)

    rows = []
    for ev in data if isinstance(data, list) else []:
        name = ev.get("Event") or ev.get("Category") or ""
        cat = ev.get("Category") or name
        country = ev.get("Country") or ""
        ts = ev.get("Date") or ev.get("date") or ev.get("Time") or ev.get("timestamp")
        if not ts:
            continue
        ts = pd.to_datetime(ts, errors="coerce", utc=True)
        if pd.isna(ts):
            continue

        cl = (cat or "").lower()
        if "cpi" in cl or "inflation" in cl:
            et, impact = "CPI", "High"
        elif "pce" in cl:
            et, impact = "PCE", "High"
        elif "non farm" in cl or "payroll" in cl:
            et, impact = "NFP", "High"
        elif "gdp" in cl:
            et, impact = "GDP", "High"
        elif "unemployment" in cl or "jobless" in cl:
            et, impact = "UNEMPLOYMENT", "High"
        elif "interest rate" in cl or "fed funds" in cl or "rate decision" in cl or "fomc" in cl:
            et, impact = "FOMC", "High"
        elif "pmi" in cl or "ism" in cl:
            et, impact = "PMI", "Medium"
        elif "confidence" in cl or "sentiment" in cl:
            et, impact = "CONSUMER_SENTIMENT", "Medium"
        else:
            continue

        actual = ev.get("Actual")
        forecast = ev.get("Forecast")
        previous = ev.get("Previous")

        pol = "neutral"
        try:
            if actual is not None and forecast is not None:
                a = float(actual); f = float(forecast)
                diff = a - f
                if et in ("CPI","PCE","UNEMPLOYMENT","FOMC"):
                    pol = "bullish" if diff < 0 else ("bearish" if diff > 0 else "neutral")
                else:
                    pol = "bullish" if diff > 0 else ("bearish" if diff < 0 else "neutral")
        except Exception:
            pol = "neutral"

        rows.append({
            "timestamp": ts,
            "ticker": "MACRO",
            "event_type": et,
            "event_name": f"{name} ({country})".strip(),
            "value": actual,
            "forecast": forecast,
            "previous": previous,
            "polarity": _normalize_polarity(pol),
            "impact": impact,
            "source": "tradingeconomics",
        })

    df = pd.DataFrame(rows, columns=CANON_COLS)
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df.sort_values("timestamp", inplace=True)
    return df

def _fetch_fred_events(start: datetime, end: datetime) -> pd.DataFrame:
    try:
        from fredapi import Fred
    except Exception:
        return pd.DataFrame(columns=CANON_COLS)

    key = os.environ.get("FRED_API_KEY")
    if not key:
        return pd.DataFrame(columns=CANON_COLS)

    fred = Fred(api_key=key)

    indicators = {
        "UNRATE": ("UNEMPLOYMENT", "Unemployment Rate", "High", True),
        "PAYEMS": ("NFP", "Nonfarm Payrolls", "High", False),
        "CPIAUCSL": ("CPI", "CPI", "High", True),
        "PCEPI": ("PCE", "PCE", "High", True),
        "UMCSENT": ("CONSUMER_SENTIMENT", "Consumer Sentiment", "Medium", False),
        "GDPC1": ("GDP", "Real GDP", "High", False),
    }

    rows = []
    prev = {}
    for series_id, (etype, ename, impact, lower_is_bullish) in indicators.items():
        try:
            s = fred.get_series(series_id, observation_start=start, observation_end=end)
        except Exception:
            continue
        if s is None or len(s) == 0:
            continue
        for ts, val in s.items():
            if pd.isna(val):
                continue
            ts = pd.to_datetime(ts, utc=True)
            last = prev.get(series_id)
            pol = "neutral"
            try:
                if last is not None:
                    change = float(val) - float(last)
                    if abs(change) > 1e-12:
                        if lower_is_bullish:
                            pol = "bullish" if change < 0 else "bearish"
                        else:
                            pol = "bullish" if change > 0 else "bearish"
            except Exception:
                pol = "neutral"
            rows.append({
                "timestamp": ts,
                "ticker": "MACRO",
                "event_type": etype,
                "event_name": ename,
                "value": float(val),
                "forecast": None,
                "previous": float(last) if last is not None else None,
                "polarity": _normalize_polarity(pol),
                "impact": impact,
                "source": "fred",
            })
            prev[series_id] = float(val)

    df = pd.DataFrame(rows, columns=CANON_COLS)
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df.sort_values("timestamp", inplace=True)
    return df

def fetch_macros(*, start: datetime, end: datetime, cfg: MacroConfig) -> pd.DataFrame:
    """
    Production macro fetching with dual redundancy.
    Uses: Trading Economics → FRED
    
    100% API-driven, no manual calendars.
    """
    try:
        from .production_macro import fetch_macro_events
        # Get event types from config
        # Important: Empty list [] means "no events", not "all events"
        event_types = cfg.include_event_types
        return fetch_macro_events(start, end, event_types)
    except ImportError:
        # Fallback: use local function
        print("[WARNING] production_macro module not available, using fallback")
        dfs = []
        if cfg.redundant_sources:
            dfs.append(_fetch_te_calendar(start, end))
            dfs.append(_fetch_fred_events(start, end))
        else:
            dfs.append(_fetch_te_calendar(start, end))
        
        if not dfs:
            return pd.DataFrame(columns=CANON_COLS)
        
        combined = pd.concat(dfs, ignore_index=True)
        if combined.empty:
            return combined
        
        # Filter by event types if specified
        if cfg.include_event_types:
            combined = combined[combined['event_type'].isin(cfg.include_event_types)]
        
        combined.sort_values("timestamp", inplace=True)
        return combined