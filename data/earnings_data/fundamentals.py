from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Dict, Any
import yfinance as yf


def get_fundamentals_snapshot(symbol: str, last_price: float | None = None) -> dict:
    """
    Best-effort fundamentals snapshot using yfinance.info.
    Returns:
      pe_ratio, eps_ttm, debt_per_share
    Notes:
      - eps_ttm uses trailingEps if present; else approximates as price / P/E when possible.
    """
    t = yf.Ticker(symbol)
    info = getattr(t, "info", {}) or {}

    pe = info.get("trailingPE", None) or info.get("forwardPE", None)
    eps = info.get("trailingEps", None)
    total_debt = info.get("totalDebt", None)
    shares_out = info.get("sharesOutstanding", None)

    debt_per_share = None
    if total_debt is not None and shares_out not in (None, 0):
        try:
            debt_per_share = float(total_debt) / float(shares_out)
        except Exception:
            debt_per_share = None

    # EPS approximation if missing
    if eps in (None, 0) and pe not in (None, 0) and last_price not in (None, 0):
        try:
            eps = float(last_price) / float(pe)
        except Exception:
            eps = None

    return {
        "pe_ratio": pe,
        "eps_ttm": eps,
        "debt_per_share": debt_per_share
    }
