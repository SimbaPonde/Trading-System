from __future__ import annotations
import os
from dataclasses import dataclass
import pandas as pd
import yfinance as yf

@dataclass
class PriceConfig:
    cache_dir: str = "price_cache"

def _cache_path(ticker: str, interval: str, cache_dir: str) -> str:
    safe = ticker.replace("/", "_")
    return os.path.join(cache_dir, f"{safe}_{interval}.parquet")

def ensure_cached(ticker: str, *, interval: str, start: pd.Timestamp, end: pd.Timestamp, cfg: PriceConfig) -> str:
    os.makedirs(cfg.cache_dir, exist_ok=True)
    path = _cache_path(ticker, interval, cfg.cache_dir)

    if os.path.exists(path):
        try:
            df = pd.read_parquet(path)
            if not df.empty:
                df.index = pd.to_datetime(df.index, utc=True)
                if df.index.min() <= start and df.index.max() >= end:
                    return path
        except Exception:
            pass

    df = yf.download(ticker, start=start, end=end, interval=interval, progress=False, auto_adjust=True)
    if df is None or df.empty:
        raise RuntimeError(f"No price data for {ticker} ({interval}) in {start.date()}..{end.date()}")
    df = df.copy()
    
    # Flatten MultiIndex columns if present (yfinance sometimes returns MultiIndex)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    df.index = pd.to_datetime(df.index, utc=True)
    df.to_parquet(path)
    return path

def load_history(ticker: str, *, interval: str, start: pd.Timestamp, end: pd.Timestamp, cfg: PriceConfig) -> pd.DataFrame:
    path = ensure_cached(ticker, interval=interval, start=start, end=end, cfg=cfg)
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index, utc=True)
    return df[(df.index >= start) & (df.index <= end)].copy()
