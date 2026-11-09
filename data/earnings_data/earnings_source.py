from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf


def _make_tz_naive(s: pd.Series) -> pd.Series:
    """
    Convert a datetime-like Series to tz-naive (datetime64[ns]).
    Handles tz-aware Series (e.g., America/New_York) and mixed inputs safely.
    """
    s = pd.to_datetime(s, errors="coerce")

    # If tz-aware (dtype: datetime64[ns, TZ]), convert to UTC then drop tz
    try:
        tz = getattr(s.dt, "tz", None)
        if tz is not None:
            return s.dt.tz_convert("UTC").dt.tz_localize(None)
    except Exception:
        pass

    # If tz-naive already, ensure tz-localize(None) doesn't crash
    try:
        return s.dt.tz_localize(None)
    except Exception:
        return s


def get_earnings_events(symbol: str, start_date, end_date) -> pd.DataFrame:
    """
    Returns a DataFrame of earnings events with:
      symbol, announce_datetime, eps_estimate, eps_actual, eps_surprise_pct, guidance_change

    Source: Yahoo Finance via yfinance.get_earnings_dates
    """
    t = yf.Ticker(symbol)

    # yfinance: get_earnings_dates(limit=...)
    try:
        df = t.get_earnings_dates(limit=24)
    except Exception:
        df = None

    if df is None or df.empty:
        return pd.DataFrame(
            columns=[
                "symbol",
                "announce_datetime",
                "eps_estimate",
                "eps_actual",
                "eps_surprise_pct",
                "guidance_change",
            ]
        )

    df = df.copy()

    # Index often is earnings datetime
    if not isinstance(df.index, pd.DatetimeIndex):
        try:
            df.index = pd.to_datetime(df.index)
        except Exception:
            pass

    df = df.reset_index().rename(columns={"index": "announce_datetime"})

    # Some yfinance versions include "Earnings Date" column
    if "Earnings Date" in df.columns:
        df["announce_datetime"] = df["Earnings Date"]
    # Ensure tz-naive announce_datetime
    df["announce_datetime"] = _make_tz_naive(df["announce_datetime"])

    # Normalize columns
    colmap = {
        "EPS Estimate": "eps_estimate",
        "Reported EPS": "eps_actual",
        "Surprise(%)": "eps_surprise_pct",
        "Surprise (%)": "eps_surprise_pct",
    }
    for k, v in colmap.items():
        if k in df.columns and v not in df.columns:
            df[v] = df[k]

    for c in ["eps_estimate", "eps_actual", "eps_surprise_pct"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # If surprise pct missing, compute
    if "eps_surprise_pct" not in df.columns or df["eps_surprise_pct"].isna().all():
        est = df.get("eps_estimate")
        act = df.get("eps_actual")
        if est is None or act is None:
            df["eps_surprise_pct"] = np.nan
        else:
            df["eps_surprise_pct"] = np.where(
                (est.notna()) & (act.notna()) & (est.abs() > 1e-9),
                (act - est) / est.abs(),
                np.nan,
            )

    df["symbol"] = symbol.upper()

    # Best-effort placeholder (strategy maps strings to numeric)
    if "guidance_change" not in df.columns:
        df["guidance_change"] = "maintained"
    df["guidance_change"] = df["guidance_change"].fillna("maintained").astype(str)

    df = df[
        [
            "symbol",
            "announce_datetime",
            "eps_estimate",
            "eps_actual",
            "eps_surprise_pct",
            "guidance_change",
        ]
    ].copy()

    # Ensure bounds are tz-naive too
    start_ts = pd.Timestamp(start_date).tz_localize(None)
    end_ts = (pd.Timestamp(end_date) + pd.Timedelta(days=1)).tz_localize(None)

    # Filter window
    df = df[(df["announce_datetime"] >= start_ts) & (df["announce_datetime"] <= end_ts)].copy()

    return df.reset_index(drop=True)
