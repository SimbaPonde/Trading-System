from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd
import yfinance as yf


@dataclass
class PriceLoadResult:
    prices: Dict[str, pd.DataFrame]  # symbol -> OHLCV daily
    start: pd.Timestamp
    end: pd.Timestamp


def _cache_path(cache_dir: Path, symbol: str) -> Path:
    return cache_dir / f"{symbol}_1d.parquet"


def load_daily_prices(
    symbols: list[str],
    start_date,
    end_date,
    cache_dir: str | Path = "cache",
    use_cache: bool = True
) -> PriceLoadResult:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Normalize to timezone-naive for comparison (yfinance returns tz-naive)
    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date)
    
    # Remove timezone info if present for comparison
    if start_ts.tzinfo is not None:
        start_ts = start_ts.tz_localize(None)
    if end_ts.tzinfo is not None:
        end_ts = end_ts.tz_localize(None)

    out: Dict[str, pd.DataFrame] = {}

    for sym in symbols:
        p = _cache_path(cache_dir, sym)
        df: Optional[pd.DataFrame] = None

        if use_cache and p.exists():
            try:
                df = pd.read_parquet(p)
                df.index = pd.to_datetime(df.index)
                # Ensure timezone-naive
                if hasattr(df.index, 'tz') and df.index.tz is not None:
                    df.index = df.index.tz_localize(None)
            except Exception:
                df = None

        if df is None or df.empty or df.index.min() > start_ts or df.index.max() < end_ts:
            # fetch a little padding
            fetch_start = (start_ts - pd.Timedelta(days=10)).date()
            fetch_end = (end_ts + pd.Timedelta(days=1)).date()
            dl = yf.download(sym, start=str(fetch_start), end=str(fetch_end), interval="1d", auto_adjust=False, progress=False)
            if dl is None or dl.empty:
                continue
            dl.index = pd.to_datetime(dl.index)
            # Ensure timezone-naive
            if hasattr(dl.index, 'tz') and dl.index.tz is not None:
                dl.index = dl.index.tz_localize(None)
                
            # --- Flatten columns if yfinance returns MultiIndex (tuples) ---
            if isinstance(dl.columns, pd.MultiIndex):
                # often looks like ('Open','AAPL'), keep only first level
                dl.columns = [c[0] for c in dl.columns]

            # Normalize column names safely
            dl.columns = [str(c).strip() for c in dl.columns]

            # Standardize to Title Case: Open, High, Low, Close, Adj Close, Volume
            dl = dl.rename(columns={c: c.title() for c in dl.columns})

            cols = [c for c in ["Open","High","Low","Close","Adj Close","Volume"] if c in dl.columns]
            dl = dl[cols].copy()
            df = dl
            try:
                df.to_parquet(p)
            except Exception:
                # fallback
                df.to_pickle(p.with_suffix(".pkl"))

        # trim - now both are timezone-naive
        df = df[(df.index >= start_ts) & (df.index <= end_ts)].copy()
        out[sym] = df

    return PriceLoadResult(prices=out, start=start_ts, end=end_ts)
