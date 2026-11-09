from __future__ import annotations
from dataclasses import dataclass
import pandas as pd

@dataclass
class ExitConfig:
    take_profit_r_multiple: float = 2.0
    stop_loss_r_multiple: float = 1.0
    time_exit_bars: int = 20

def simulate_exits(trades: pd.DataFrame, prices: dict, cfg: ExitConfig) -> pd.DataFrame:
    if trades.empty:
        return trades

    trades = trades.copy()
    
    # Initialize columns
    trades["exit_time"] = pd.NaT
    trades["exit_price"] = None
    trades["exit_reason"] = "time_limit"
    trades["bars_held"] = 0
    trades["pnl"] = 0.0

    for idx, tr in trades.iterrows():
        t = tr["ticker"]
        if t not in prices or prices[t].empty:
            continue
        df = prices[t].copy()
        df.index = pd.to_datetime(df.index)

        entry_time = pd.to_datetime(tr["entry_time"])
        entry_price = float(tr["entry_price"])
        side = tr["side"]
        stop_dist = float(tr.get("stop_dist") or 0.0)
        if stop_dist <= 0:
            stop_dist = max(0.01 * entry_price, 1e-6)

        if side == "BUY":
            stop = entry_price - cfg.stop_loss_r_multiple * stop_dist
            tp = entry_price + cfg.take_profit_r_multiple * stop_dist
        else:
            stop = entry_price + cfg.stop_loss_r_multiple * stop_dist
            tp = entry_price - cfg.take_profit_r_multiple * stop_dist

        path = df[df.index >= entry_time].head(cfg.time_exit_bars + 1)
        if path.empty:
            continue

        exit_px = float(path["Close"].iloc[-1])
        exit_ts = path.index[-1]
        exit_reason = "time_limit"
        bars_held = len(path) - 1

        for bar_idx, (ts, row) in enumerate(path.iterrows()):
            hi = float(row.get("High", row["Close"]))
            lo = float(row.get("Low", row["Close"]))
            if side == "BUY":
                if lo <= stop:
                    exit_px, exit_ts = stop, ts
                    exit_reason = "stop_loss"
                    bars_held = bar_idx
                    break
                if hi >= tp:
                    exit_px, exit_ts = tp, ts
                    exit_reason = "take_profit"
                    bars_held = bar_idx
                    break
            else:
                if hi >= stop:
                    exit_px, exit_ts = stop, ts
                    exit_reason = "stop_loss"
                    bars_held = bar_idx
                    break
                if lo <= tp:
                    exit_px, exit_ts = tp, ts
                    exit_reason = "take_profit"
                    bars_held = bar_idx
                    break

        size = int(tr["size"])
        pnl = (exit_px - entry_price) * size if side == "BUY" else (entry_price - exit_px) * size
        
        # Convert to timezone-naive datetime for assignment (no pandas warnings)
        if hasattr(exit_ts, 'tz_localize'):
            # It's a pandas Timestamp
            exit_time_naive = exit_ts.tz_localize(None) if exit_ts.tzinfo else exit_ts
        else:
            # Convert to pandas Timestamp first, then strip timezone
            exit_time_naive = pd.Timestamp(exit_ts).tz_localize(None)
        
        trades.at[idx, "exit_time"] = exit_time_naive
        trades.at[idx, "exit_price"] = float(exit_px)
        trades.at[idx, "exit_reason"] = exit_reason
        trades.at[idx, "bars_held"] = int(bars_held)
        trades.at[idx, "pnl"] = float(pnl)
    
    # Convert exit_time column to timezone-aware after all assignments
    if not trades.empty and trades["exit_time"].notna().any():
        trades["exit_time"] = pd.to_datetime(trades["exit_time"]).dt.tz_localize('UTC')

    return trades