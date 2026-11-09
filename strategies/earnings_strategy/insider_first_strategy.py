from __future__ import annotations
from dataclasses import dataclass
from typing import Dict
import numpy as np
import pandas as pd


@dataclass
class InsiderFirstConfig:
    min_conviction: float = 0.45
    max_new_positions_per_day: int = 5
    stop_loss_pct: float = 0.10
    take_profit_pct: float = 0.25
    max_holding_days: int = 20

    min_net_buy_90d_usd: float = 500_000.0
    min_opportunistic_ratio_90d: float = 0.60
    min_unique_buyers_90d: int = 2

    insider_value_scale_usd: float = 2_000_000.0

    max_pe_ratio: float = 80.0
    max_debt_per_share: float = 200.0


def _norm01_safe(s: pd.Series) -> pd.Series:
    mn = s.min()
    mx = s.max()
    if pd.isna(mn) or pd.isna(mx) or (mx - mn) < 1e-9:
        return pd.Series(0.5, index=s.index)
    return (s - mn) / (mx - mn)


def build_insider_daily_agg(insider_trades: pd.DataFrame, *, use_filing_date: bool = True) -> pd.DataFrame:
    if insider_trades is None or insider_trades.empty:
        return pd.DataFrame(columns=[
            "symbol","event_date","buy_value","sell_value","net_value",
            "opportunistic_buy_value","routine_buy_value","buy_count","sell_count","unique_buyers"
        ])

    df = insider_trades.copy()
    df["symbol"] = df.get("symbol", "").astype(str).str.upper().str.strip()

    date_col = "filing_date" if (use_filing_date and "filing_date" in df.columns) else "trade_date"
    df["event_date"] = pd.to_datetime(df.get(date_col), errors="coerce").dt.normalize()

    df["transaction_type"] = df.get("transaction_type", "").astype(str).str.upper().str.strip()
    df["value_usd"] = pd.to_numeric(df.get("value_usd"), errors="coerce").fillna(0.0)
    df["is_routine"] = df.get("is_routine", False).astype(bool)

    BUY_CODES = {"P", "M"}
    SELL_CODES = {"S"}

    df["buy_value"] = np.where(df["transaction_type"].isin(BUY_CODES), df["value_usd"], 0.0)
    df["sell_value"] = np.where(df["transaction_type"].isin(SELL_CODES), df["value_usd"], 0.0)
    df["opportunistic_buy_value"] = np.where(
        df["transaction_type"].isin(BUY_CODES) & (~df["is_routine"]),
        df["value_usd"],
        0.0
    )
    df["routine_buy_value"] = np.where(
        df["transaction_type"].isin(BUY_CODES) & (df["is_routine"]),
        df["value_usd"],
        0.0
    )
    df["buy_count"] = df["transaction_type"].isin(BUY_CODES).astype(int)
    df["sell_count"] = df["transaction_type"].isin(SELL_CODES).astype(int)

    if "insider_name" in df.columns:
        ub = (
            df[df["transaction_type"].isin(BUY_CODES)]
            .groupby(["symbol","event_date"])["insider_name"]
            .nunique()
            .rename("unique_buyers")
        )
    else:
        ub = (
            df[df["transaction_type"].isin(BUY_CODES)]
            .groupby(["symbol","event_date"])
            .size()
            .rename("unique_buyers")
        )

    agg = df.groupby(["symbol","event_date"], as_index=False)[
        ["buy_value","sell_value","opportunistic_buy_value","routine_buy_value","buy_count","sell_count"]
    ].sum()
    agg = agg.merge(ub.reset_index(), on=["symbol","event_date"], how="left")
    agg["unique_buyers"] = agg["unique_buyers"].fillna(0).astype(int)
    agg["net_value"] = agg["buy_value"] - agg["sell_value"]
    agg = agg.dropna(subset=["event_date"])
    return agg


def score_insider_first(
    prices_daily: Dict[str, pd.DataFrame],
    insider_trades: pd.DataFrame,
    fundamentals_df: pd.DataFrame,
    cfg: InsiderFirstConfig,
    *,
    use_filing_date: bool = True
) -> pd.DataFrame:
    daily = build_insider_daily_agg(insider_trades, use_filing_date=use_filing_date)
    if daily.empty:
        return pd.DataFrame()

    out_rows = []
    for sym in daily["symbol"].unique():
        sym_daily = daily[daily["symbol"] == sym].set_index("event_date").sort_index()
        if sym_daily.empty:
            continue

        idx = pd.date_range(sym_daily.index.min(), sym_daily.index.max(), freq="D")
        sym_daily = sym_daily.reindex(idx).fillna(0.0)
        sym_daily["symbol"] = sym

        sym_daily["net_buy_90d"] = sym_daily["net_value"].rolling(90, min_periods=1).sum()
        sym_daily["opportunistic_buy_90d"] = sym_daily["opportunistic_buy_value"].rolling(90, min_periods=1).sum()
        sym_daily["routine_buy_90d"] = sym_daily["routine_buy_value"].rolling(90, min_periods=1).sum()
        sym_daily["unique_buyers_90d"] = sym_daily["unique_buyers"].rolling(90, min_periods=1).max()

        sym_daily = sym_daily.reset_index().rename(columns={"index": "event_date"})
        out_rows.append(sym_daily[[
            "symbol","event_date","net_buy_90d","opportunistic_buy_90d","routine_buy_90d","unique_buyers_90d"
        ]])

    scored = pd.concat(out_rows, ignore_index=True) if out_rows else pd.DataFrame()
    if scored.empty:
        return pd.DataFrame()

    scored["opportunistic_ratio_90d"] = np.where(
        (scored["opportunistic_buy_90d"] + scored["routine_buy_90d"]) > 0,
        scored["opportunistic_buy_90d"] / (scored["opportunistic_buy_90d"] + scored["routine_buy_90d"]),
        0.0
    )
    scored["cluster_buy_flag_90d"] = (scored["unique_buyers_90d"] >= int(cfg.min_unique_buyers_90d)).astype(int)

    scale = float(cfg.insider_value_scale_usd) if cfg.insider_value_scale_usd else 2_000_000.0
    net_scale = np.tanh(scored["net_buy_90d"] / max(scale, 1.0))
    opp_scale = scored["opportunistic_ratio_90d"].clip(0, 1)
    cluster = scored["cluster_buy_flag_90d"].clip(0, 1)
    scored["insider_score"] = (0.60 * net_scale + 0.30 * opp_scale + 0.10 * cluster).clip(0, 1)

    f = fundamentals_df.copy() if fundamentals_df is not None else pd.DataFrame(columns=["symbol","pe_ratio","eps_ttm","debt_per_share"])
    if not f.empty:
        f["symbol"] = f["symbol"].astype(str).str.upper().str.strip()
    scored = scored.merge(f, on="symbol", how="left")

    scored["pe_ratio"] = pd.to_numeric(scored.get("pe_ratio"), errors="coerce")
    scored["eps_ttm"] = pd.to_numeric(scored.get("eps_ttm"), errors="coerce")
    scored["debt_per_share"] = pd.to_numeric(scored.get("debt_per_share"), errors="coerce")

    scored["N_pe"] = 1.0 - scored.groupby("event_date")["pe_ratio"].transform(_norm01_safe).fillna(0.5)
    scored["N_eps"] = scored.groupby("event_date")["eps_ttm"].transform(_norm01_safe).fillna(0.5)
    scored["N_debt"] = 1.0 - scored.groupby("event_date")["debt_per_share"].transform(_norm01_safe).fillna(0.5)
    scored["fundamentals_score"] = (0.35 * scored["N_pe"] + 0.45 * scored["N_eps"] + 0.20 * scored["N_debt"]).clip(0, 1)

    pe_ok = scored["pe_ratio"].isna() | (scored["pe_ratio"] <= float(cfg.max_pe_ratio))
    debt_ok = scored["debt_per_share"].isna() | (scored["debt_per_share"] <= float(cfg.max_debt_per_share))

    scored["eligible"] = (
        (scored["cluster_buy_flag_90d"] == 1) &
        (scored["net_buy_90d"] >= float(cfg.min_net_buy_90d_usd)) &
        (scored["opportunistic_ratio_90d"] >= float(cfg.min_opportunistic_ratio_90d)) &
        pe_ok & debt_ok
    )

    scored["conviction_score"] = (0.70 * scored["insider_score"] + 0.30 * scored["fundamentals_score"]).clip(0, 1)
    scored["category"] = "insider_first"
    scored = scored.sort_values(["event_date","conviction_score"], ascending=[True, False]).reset_index(drop=True)
    return scored
