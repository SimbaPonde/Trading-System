import pandas as pd
import yfinance as yf
from typing import Dict, Tuple, Optional
from datetime import datetime, timedelta

from .config.config import MeanReversionParams, AssetClass
from .mean_reversion import MeanReversionStrategy


# ---------------------------
# Helpers: yfinance cleanup
# ---------------------------
def _flatten_yf(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    # MultiIndex columns -> first level (Open/High/Low/Close/Volume)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.rename(columns=str.title)

    # If duplicates cause df["Close"] to become a DataFrame, pick first
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col in df.columns and isinstance(df[col], pd.DataFrame):
            df[col] = df[col].iloc[:, 0]

    return df


def load_price_data(symbols, start: str, end: str, interval: str) -> Dict[str, pd.DataFrame]:
    out: Dict[str, pd.DataFrame] = {}
    for sym in symbols:
        df = yf.download(
            sym,
            start=start,
            end=end,
            interval=interval,
            auto_adjust=True,
            progress=False,
            group_by="column",
            threads=True,
        )
        if df is None or df.empty:
            continue

        df = _flatten_yf(df).dropna()

        required = {"Open", "High", "Low", "Close"}
        if not required.issubset(df.columns):
            continue

        out[sym] = df
    return out


# ---------------------------
# Backtest engine
# ---------------------------
class BacktestEngine:
    def __init__(self, prices: Dict[str, pd.DataFrame], *, initial_balance: float, params: MeanReversionParams):
        self.prices = prices
        self.initial_balance = float(initial_balance)
        self.params = params

    def _simulate_trade_bar_by_bar(self, df: pd.DataFrame, signal, size: float) -> Tuple[float, pd.Timestamp]:
        """
        Realistic stop/TP simulation using High/Low.
        Conservative intrabar rule: STOP checked before TP for longs; for shorts, STOP checked before TP.
        If never hit, exit at last Close.
        Returns (pnl, exit_time).
        """
        entry_loc = df.index.get_loc(signal.time)

        for i in range(entry_loc + 1, len(df)):
            high = float(df.iloc[i]["High"])
            low = float(df.iloc[i]["Low"])
            t = df.index[i]

            if signal.side == "BUY":
                if low <= signal.stop_loss:
                    return (signal.stop_loss - signal.price) * size, t
                if high >= signal.take_profit:
                    return (signal.take_profit - signal.price) * size, t
            else:  # SELL
                if high >= signal.stop_loss:
                    return (signal.price - signal.stop_loss) * size, t
                if low <= signal.take_profit:
                    return (signal.price - signal.take_profit) * size, t

        final_close = float(df.iloc[-1]["Close"])
        final_t = df.index[-1]
        pnl = (final_close - signal.price) * size if signal.side == "BUY" else (signal.price - final_close) * size
        return pnl, final_t

    def run(self, strategy: MeanReversionStrategy) -> Tuple[pd.DataFrame, dict]:
        equity = self.initial_balance
        trades = []
        curve = []

        risk_pct = float(self.params.position_risk_pct)

        for symbol, df in self.prices.items():
            if df is None or df.empty:
                continue

            signals = strategy.generate_signals(df, ticker=symbol)

            for s in signals:
                # Risk-based sizing
                risk_amount = equity * risk_pct
                stop_dist = abs(float(s.price) - float(s.stop_loss))
                if stop_dist <= 0:
                    continue

                size = risk_amount / stop_dist

                pnl, exit_time = self._simulate_trade_bar_by_bar(df, s, size)
                equity += pnl

                trades.append(
                    {
                        "ticker": s.ticker,
                        "entry_time": s.time,
                        "exit_time": exit_time,
                        "side": s.side,
                        "entry": float(s.price),
                        "stop": float(s.stop_loss),
                        "tp": float(s.take_profit),
                        "size": float(size),
                        "pnl": float(pnl),
                        "equity": float(equity),
                        "reason": s.reason,
                    }
                )
                curve.append(equity)

        trades_df = pd.DataFrame(trades)
        curve_s = pd.Series(curve, dtype="float64")

        summary = {
            "initial_equity": float(self.initial_balance),
            "final_equity": float(equity),
            "return_%": (equity / self.initial_balance - 1.0) * 100.0,
            "total_trades": int(len(trades_df)),
            "max_drawdown_%": (
                float(((curve_s.cummax() - curve_s) / curve_s.cummax()).max() * 100.0)
                if not curve_s.empty
                else 0.0
            ),
        }

        return trades_df, summary


# ============================================================
# ✅ THIS is what main.py imports:
# from strategies.backtest import run_backtest
# ============================================================
def run_backtest(
    *,
    tickers,
    interval,
    initial_balance,
    asset_type,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    lookback_days: Optional[int] = None,
):
    # Resolve dates
    if start_date is None or end_date is None:
        lookback_days = int(lookback_days or 30)
        end_dt = datetime.today()
        start_dt = end_dt - timedelta(days=lookback_days)
        start_date = start_dt.strftime("%Y-%m-%d")
        end_date = end_dt.strftime("%Y-%m-%d")

    prices = load_price_data(tickers, start_date, end_date, interval)

    asset_class = {
        "stocks": AssetClass.STOCK,
        "forex": AssetClass.FOREX,
        "crypto": AssetClass.CRYPTO,
    }.get(asset_type, AssetClass.STOCK)

    params = MeanReversionParams()
    strategy = MeanReversionStrategy(params=params, asset_class=asset_class)

    engine = BacktestEngine(prices, initial_balance=float(initial_balance), params=params)
    return engine.run(strategy)
