from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Tuple, List, Optional
import numpy as np
import pandas as pd


@dataclass
class StrategyConfig:
    # shared risk/portfolio controls
    min_conviction: float = 0.45
    max_new_positions_per_day: int = 5
    stop_loss_pct: float = 0.10
    take_profit_pct: float = 0.25
    max_holding_days: int = 20

    # earnings/insider scoring thresholds
    strong_earnings_cutoff: float = 0.62
    confirm_earnings_cutoff: float = 0.52
    confirm_insider_cutoff: float = 0.45
    insider_value_scale_usd: float = 2_000_000.0

    # mode/category
    mode: str = "earnings_insider"  # earnings_only | earnings_insider

    # hybrid earnings scoring blend: xs weight reaches 1 when >= this many names report that day
    xs_full_strength_n: int = 10


def map_guidance_to_numeric(x) -> float:
    if x is None:
        return 0.0
    s = str(x).strip().lower()
    if s in ("raised", "raise", "up", "higher", "increase"):
        return 1.0
    if s in ("lowered", "lower", "down", "reduced", "decrease"):
        return -1.0
    if s in ("maintained", "flat", "unchanged", "in-line", "inline"):
        return 0.0
    try:
        return float(s)
    except Exception:
        return 0.0


def _norm01_safe(s: pd.Series) -> pd.Series:
    mn = s.min()
    mx = s.max()
    if pd.isna(mn) or pd.isna(mx) or (mx - mn) < 1e-9:
        return pd.Series(0.5, index=s.index)
    return (s - mn) / (mx - mn)


def _abs_surprise_to01(x: pd.Series) -> pd.Series:
    return ((x + 1.0) / 2.0).clip(0, 1)


def _abs_return_to01(r: pd.Series) -> pd.Series:
    return ((r + 0.25) / 0.50).clip(0, 1)


def build_insider_features(insider_trades: pd.DataFrame) -> pd.DataFrame:
    if insider_trades is None or insider_trades.empty:
        return pd.DataFrame(columns=[
            "symbol","trade_date","buy_value","sell_value","net_value","buy_count","sell_count",
            "unique_buyers","opportunistic_buy_value","routine_buy_value"
        ])

    df = insider_trades.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.normalize()
    df["value_usd"] = pd.to_numeric(df.get("value_usd"), errors="coerce").fillna(0.0)
    df["is_routine"] = df.get("is_routine", False).astype(bool)
    df["transaction_type"] = df.get("transaction_type", "").astype(str).str.upper().str.strip()
    df["symbol"] = df.get("symbol", "").astype(str).str.upper().str.strip()

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
            .groupby(["symbol","trade_date"])["insider_name"]
            .nunique()
            .rename("unique_buyers")
        )
    else:
        ub = (
            df[df["transaction_type"].isin(BUY_CODES)]
            .groupby(["symbol","trade_date"])
            .size()
            .rename("unique_buyers")
        )

    agg = df.groupby(["symbol","trade_date"], as_index=False)[
        ["buy_value","sell_value","opportunistic_buy_value","routine_buy_value","buy_count","sell_count"]
    ].sum()

    agg = agg.merge(ub.reset_index(), on=["symbol","trade_date"], how="left")
    agg["unique_buyers"] = agg["unique_buyers"].fillna(0).astype(int)
    agg["net_value"] = agg["buy_value"] - agg["sell_value"]
    return agg


def _compute_insider_scores(scored: pd.DataFrame, insider_trades: pd.DataFrame, cfg: StrategyConfig) -> pd.DataFrame:
    if cfg.mode == "earnings_only":
        scored["insider_score"] = 0.0
        scored["net_buy_90d"] = 0.0
        scored["opportunistic_ratio_90d"] = 0.0
        scored["cluster_buy_flag_90d"] = 0
        return scored

    daily_agg = build_insider_features(insider_trades)
    if daily_agg.empty:
        scored["insider_score"] = 0.0
        scored["net_buy_90d"] = 0.0
        scored["opportunistic_ratio_90d"] = 0.0
        scored["cluster_buy_flag_90d"] = 0
        return scored

    daily_agg = daily_agg.copy()
    daily_agg["trade_date"] = pd.to_datetime(daily_agg["trade_date"], errors="coerce").dt.normalize()

    out_rows = []
    for sym in scored["symbol"].unique():
        sym_daily = daily_agg[daily_agg["symbol"] == sym].set_index("trade_date").sort_index()
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

    roll = pd.concat(out_rows, ignore_index=True) if out_rows else pd.DataFrame()
    scored = scored.merge(roll, on=["symbol","event_date"], how="left")

    scored["net_buy_90d"] = pd.to_numeric(scored.get("net_buy_90d"), errors="coerce").fillna(0.0)
    scored["opportunistic_buy_90d"] = pd.to_numeric(scored.get("opportunistic_buy_90d"), errors="coerce").fillna(0.0)
    scored["routine_buy_90d"] = pd.to_numeric(scored.get("routine_buy_90d"), errors="coerce").fillna(0.0)
    scored["unique_buyers_90d"] = pd.to_numeric(scored.get("unique_buyers_90d"), errors="coerce").fillna(0.0)

    scored["opportunistic_ratio_90d"] = np.where(
        (scored["opportunistic_buy_90d"] + scored["routine_buy_90d"]) > 0,
        scored["opportunistic_buy_90d"] / (scored["opportunistic_buy_90d"] + scored["routine_buy_90d"]),
        0.0
    )
    scored["cluster_buy_flag_90d"] = (scored["unique_buyers_90d"] >= 2).astype(int)

    scale = float(cfg.insider_value_scale_usd) if cfg.insider_value_scale_usd else 2_000_000.0
    net_scale = np.tanh(scored["net_buy_90d"] / max(scale, 1.0))
    opp_scale = scored["opportunistic_ratio_90d"].clip(0, 1)
    cluster = scored["cluster_buy_flag_90d"].clip(0, 1)

    scored["insider_score"] = (0.55 * net_scale + 0.35 * opp_scale + 0.10 * cluster).clip(0, 1)
    return scored


def score_signals(
    prices_daily: Dict[str, pd.DataFrame],
    earnings_events: pd.DataFrame,
    insider_trades: pd.DataFrame,
    fundamentals_df: pd.DataFrame,
    cfg: StrategyConfig
) -> pd.DataFrame:
    if earnings_events is None or earnings_events.empty:
        return pd.DataFrame()

    ev = earnings_events.copy()
    ev["symbol"] = ev["symbol"].astype(str).str.upper().str.strip()
    ev["announce_datetime"] = pd.to_datetime(ev["announce_datetime"], errors="coerce")
    ev["event_date"] = ev["announce_datetime"].dt.normalize()
    ev["eps_surprise_pct"] = pd.to_numeric(ev["eps_surprise_pct"], errors="coerce")
    ev["G_scaled"] = ev.get("guidance_change", "maintained").apply(map_guidance_to_numeric).clip(-1, 1)

    gap_rows = []
    for sym in ev["symbol"].unique():
        px = prices_daily.get(sym)
        if px is None or px.empty:
            continue
        p = px.copy()
        p.index = pd.to_datetime(p.index, errors="coerce")
        p = p.sort_index()
        p["event_date"] = p.index.normalize()
        p = p.drop_duplicates(subset=["event_date"], keep="last")
        p["prev_close"] = p["Close"].shift(1)
        p["day_return"] = (p["Close"] / p["prev_close"] - 1.0)
        tmp = p[["event_date","day_return"]].copy()
        tmp["symbol"] = sym
        gap_rows.append(tmp)

    gap_df = pd.concat(gap_rows, ignore_index=True) if gap_rows else pd.DataFrame(columns=["symbol","event_date","day_return"])
    scored = ev.merge(gap_df, on=["symbol","event_date"], how="left")
    scored["day_return"] = pd.to_numeric(scored["day_return"], errors="coerce").clip(-0.25, 0.25)

    scored["surprise_clip"] = scored["eps_surprise_pct"].clip(-1.0, 1.0)

    # Hybrid earnings score: stable for small universes AND good for large universes
    scored["S_abs"] = _abs_surprise_to01(scored["surprise_clip"]).fillna(0.5)
    scored["R_abs"] = _abs_return_to01(scored["day_return"]).fillna(0.5)

    scored["S_xs"] = scored.groupby("event_date")["surprise_clip"].transform(_norm01_safe).fillna(0.5)
    scored["R_xs"] = scored.groupby("event_date")["day_return"].transform(_norm01_safe).fillna(0.5)

    cnt = scored.groupby("event_date")["symbol"].transform("count").astype(float)
    full_n = float(max(cfg.xs_full_strength_n, 3))
    w = ((cnt - 2.0) / (full_n - 2.0)).clip(0.0, 1.0)

    scored["S_rank"] = (1.0 - w) * scored["S_abs"] + w * scored["S_xs"]
    scored["R_rank"] = (1.0 - w) * scored["R_abs"] + w * scored["R_xs"]

    scored["earnings_score"] = (
        0.6 * scored["S_rank"]
        + 0.3 * scored["R_rank"]
        + 0.1 * (scored["G_scaled"] + 1.0) / 2.0
    ).clip(0, 1)

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
    scored["fundamentals_score"] = (0.4 * scored["N_pe"] + 0.4 * scored["N_eps"] + 0.2 * scored["N_debt"]).clip(0, 1)

    scored = _compute_insider_scores(scored, insider_trades, cfg)

    if cfg.mode == "earnings_only":
        scored["conviction_score"] = (0.80 * scored["earnings_score"] + 0.20 * scored["fundamentals_score"]).clip(0, 1)
        scored["eligible"] = (scored["earnings_score"] >= float(cfg.confirm_earnings_cutoff))
    else:
        scored["conviction_score"] = (
            0.60 * scored["earnings_score"]
            + 0.25 * scored["insider_score"]
            + 0.15 * scored["fundamentals_score"]
        ).clip(0, 1)

        insider_min = float(cfg.confirm_insider_cutoff) * 0.60
        scored["eligible"] = (
            (scored["earnings_score"] >= float(cfg.strong_earnings_cutoff)) &
            (scored["insider_score"] >= insider_min)
        )

    scored["category"] = cfg.mode
    scored = scored.sort_values(["event_date","conviction_score"], ascending=[True, False]).reset_index(drop=True)
    return scored


def next_trading_day_open(prices: pd.DataFrame, date: pd.Timestamp) -> Optional[Tuple[pd.Timestamp, float]]:
    idx = pd.to_datetime(prices.index).normalize()
    candidates = prices.loc[idx > date]
    if candidates is None or candidates.empty:
        return None
    d = pd.to_datetime(candidates.index[0]).normalize()
    open_px = float(candidates.iloc[0]["Open"])
    return (d, open_px)


def generate_trade_list(
    prices_daily: Dict[str, pd.DataFrame],
    scored: pd.DataFrame,
    cfg: StrategyConfig
) -> List[dict]:
    if scored is None or scored.empty:
        return []

    trades = []
    rows = []
    for _, r in scored.iterrows():
        if not bool(r.get("eligible", True)):
            continue
        sym = r["symbol"]
        px = prices_daily.get(sym)
        if px is None or px.empty:
            continue
        nd = next_trading_day_open(px, pd.Timestamp(r["event_date"]))
        if not nd:
            continue
        entry_date, entry_open = nd
        rows.append((entry_date, sym, entry_open, r["event_date"], float(r["conviction_score"]), str(r.get("category", cfg.mode))))

    if not rows:
        return []

    df = pd.DataFrame(rows, columns=["entry_date","symbol","entry_price","event_date","conviction_score","category"])
    df = df[df["conviction_score"] >= float(cfg.min_conviction)].copy()

    for d, g in df.groupby("entry_date"):
        g = g.sort_values("conviction_score", ascending=False).head(int(cfg.max_new_positions_per_day))
        for _, rr in g.iterrows():
            trades.append({
                "symbol": rr["symbol"],
                "event_date": rr["event_date"],
                "entry_date": rr["entry_date"],
                "entry_price": float(rr["entry_price"]),
                "conviction_score": float(rr["conviction_score"]),
                "category": rr["category"],
                "stop_loss_pct": float(cfg.stop_loss_pct),
                "take_profit_pct": float(cfg.take_profit_pct),
                "max_holding_days": int(cfg.max_holding_days),
            })

    return trades
