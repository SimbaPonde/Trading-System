"""
app.py - Flask API Backend for AI Trading System (Backtest + Dashboard)
COMPLETE VERSION: All features working including analytics
"""

import os
import json
import threading
from datetime import datetime, timedelta

import pandas as pd
from flask import Flask, request, jsonify, send_from_directory, render_template
from flask_cors import CORS

# ---- IMPORT YOUR BACKTEST + LIVE MODULES HERE ----
try:
    from runmodes.backtest import run_backtest
except ImportError:
    try:
        from runmodes.backtest import run_backtest
    except ImportError as e:
        raise ImportError(
            "Could not import run_backtest. Make sure backtest.py exists.\n"
            f"Original error: {e}"
        )

# live trading engine is optional
try:
    from runmodes.live_trading import LiveTradingEngine
except ImportError:
    LiveTradingEngine = None

# -----------------------------------------------------------------------------
# Flask setup
# -----------------------------------------------------------------------------
app = Flask(__name__)
CORS(app)

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(APP_ROOT, "outputs")

# -----------------------------------------------------------------------------
# Backtest status (for /api/backtest/status)
# -----------------------------------------------------------------------------
backtest_status = {
    "is_running": False,
    "status": "idle",
    "progress": 0,
    "error": None,
    "results": None,
}

backtest_lock = threading.Lock()

# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------
def ensure_outputs_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_summary():
    """Read outputs/summary.json if present"""
    ensure_outputs_dir()
    path = os.path.join(OUTPUT_DIR, "summary.json")
    if not os.path.exists(path):
        return {
            "initial_balance": 100000.0,
            "final_balance": 100000.0,
            "pnl": 0.0,
            "return_pct": 0.0,
            "trades_executed": 0,
            "forced_exits": 0,
            "potentials": 0,
            "risk_regime": "NEUTRAL",
            "news_trades": 0,
            "macro_trades": 0,
            "confluence_trades": 0,
            "earnings_trades": 0,
            "quality_rejected": 0,
            "regime_rejected": 0,
            "ai_rejected": 0,
        }
    with open(path, "r") as f:
        return json.load(f)


def load_trades_df():
    """Load executed trades from outputs/trades.csv"""
    ensure_outputs_dir()
    path = os.path.join(OUTPUT_DIR, "trades.csv")
    if not os.path.exists(path):
        return pd.DataFrame()

    if os.path.getsize(path) == 0:
        return pd.DataFrame()

    try:
        return pd.read_csv(path)
    except Exception as e:
        print(f"[API] Failed to read trades.csv: {e}")
        return pd.DataFrame()


def choose_col(df, candidates):
    """Return first column name from candidates that exists in df"""
    for c in candidates:
        if c in df.columns:
            return c
    return None


def build_performance_data(trades_df, initial_balance):
    """Build equity curve for dashboard"""
    if trades_df.empty:
        return []

    pnl_col = choose_col(trades_df, ["pnl", "PnL", "pnl_dollars"])
    if pnl_col is None:
        return []

    df = trades_df.copy()
    time_col = choose_col(df, ["exit_time", "timestamp", "time", "date", "closed_at"])
    
    if time_col and time_col in df.columns:
        try:
            df[time_col] = pd.to_datetime(df[time_col])
            df = df.sort_values(time_col)
            df["cum_pnl"] = df[pnl_col].cumsum()
            df["balance"] = initial_balance + df["cum_pnl"]

            grouped = (
                df.groupby(df[time_col].dt.date)["balance"]
                .last()
                .reset_index(name="balance")
            )

            return [
                {"date": d.strftime("%Y-%m-%d"), "balance": float(b)}
                for d, b in zip(grouped[time_col], grouped["balance"])
            ]
        except Exception as e:
            print(f"[API] Failed to build time-based equity curve: {e}")

    # Fallback: index-based
    df = df.copy()
    df["cum_pnl"] = df[pnl_col].cumsum()
    return [
        {"date": str(i + 1), "balance": float(initial_balance + v)}
        for i, v in enumerate(df["cum_pnl"])
    ]


def summarize_trades(trades_df, summary):
    """High-level dashboard metrics"""
    pnl_col = choose_col(trades_df, ["pnl", "PnL", "pnl_dollars"])
    total_pnl = float(summary.get("pnl", 0.0))
    win_rate = 0.0
    active_trades = 0

    if not trades_df.empty and pnl_col:
        total_pnl = float(trades_df[pnl_col].sum())
        wins = (trades_df[pnl_col] > 0).sum()
        losses = (trades_df[pnl_col] < 0).sum()
        denom = wins + losses
        win_rate = float((wins / denom) * 100.0) if denom > 0 else 0.0

    portfolio_value = float(summary.get("final_balance", summary.get("initial_balance", 100000.0) + total_pnl))

    return {
        "portfolio_value": portfolio_value,
        "active_trades": int(active_trades),
        "win_rate": float(win_rate),
        "total_pnl": total_pnl,
    }


def map_trades_for_api(trades_df, limit=None):
    """Convert trades DataFrame to API format"""
    if trades_df.empty:
        return []

    ticker_col = choose_col(trades_df, ["ticker", "symbol"])
    side_col = choose_col(trades_df, ["side", "direction"])
    entry_col = choose_col(trades_df, ["entry", "entry_price", "open_price"])
    exit_col = choose_col(trades_df, ["exit", "exit_price", "close_price"])
    pnl_col = choose_col(trades_df, ["pnl_net", "pnl", "PnL", "pnl_dollars"])
    cat_col = choose_col(trades_df, ["strategy", "category", "type", "signal_type"])  # Fixed: Added 'strategy'
    strategy_col = choose_col(trades_df, ["strategy"])
    
    # DEBUG: Print which columns were found
    print(f"[DEBUG] Columns found: entry={entry_col}, exit={exit_col}, pnl={pnl_col}, cat={cat_col}")

    df = trades_df.copy()
    time_col = choose_col(df, ["exit_time", "timestamp", "time", "date", "closed_at"])
    
    if time_col and time_col in df.columns:
        try:
            df[time_col] = pd.to_datetime(df[time_col])
            df = df.sort_values(time_col)
        except Exception:
            pass

    if limit is not None:
        df = df.tail(limit)

    trades = []
    for idx, (_, row) in enumerate(df.iterrows()):
        # Get category, fallback to strategy if category is missing/nan
        category = str(row.get(cat_col, "")) if cat_col else ""
        if not category or category == "nan" or (cat_col and pd.isna(row.get(cat_col))):
            category = str(row.get(strategy_col, "")) if strategy_col else ""
        
        # Format category for display
        if category == "news_macro":
            category = "News"
        elif category == "mean_reversion":
            category = "Mean Reversion"
        elif category == "earnings_insider":
            category = "Earnings"
        
        trade_data = {
            "ticker": str(row.get(ticker_col, "")) if ticker_col else "",
            "side": str(row.get(side_col, "")) if side_col else "",
            "entry": float(row.get(entry_col, 0.0)) if entry_col else 0.0,
            "exit": float(row.get(exit_col, 0.0)) if exit_col else 0.0,
            "pnl": float(row.get(pnl_col, 0.0)) if pnl_col else 0.0,
            "category": category,
        }
        
        # DEBUG: Print first 3 trades
        if idx < 3:
            print(f"[DEBUG] Trade {idx}: {trade_data['ticker']} entry={trade_data['entry']:.4f} exit={trade_data['exit']:.4f} pnl={trade_data['pnl']:.2f}")
        
        trades.append(trade_data)
    return trades


def map_summary_for_frontend(summary_dict):
    """Map internal summary to frontend format"""
    if summary_dict is None:
        summary_dict = {}

    mapped = {
        "initial_balance": float(summary_dict.get("initial_balance", 100000.0)),
        "final_balance": float(summary_dict.get("final_balance", 100000.0)),
        "total_pl": float(summary_dict.get("pnl", 0.0)),
        "return_pct": float(summary_dict.get("return_pct", 0.0)),
        "trades": int(summary_dict.get("trades_executed", 0)),
        "forced_exits": int(summary_dict.get("forced_exits", 0)),
        "potentials": int(summary_dict.get("potentials", 0)),
        "risk_regime": str(summary_dict.get("risk_regime", "NEUTRAL")),
        "news_trades": int(summary_dict.get("news_trades", 0)),
        "macro_trades": int(summary_dict.get("macro_trades", 0)),
        "confluence_trades": int(summary_dict.get("confluence_trades", 0)),
        "earnings_trades": int(summary_dict.get("earnings_trades", 0)),
        "mean_reversion_trades": int(summary_dict.get("mean_reversion_trades", 0)),  # ✨ FIX: Added missing field!
        "quality_rejected": int(summary_dict.get("quality_rejected", 0)),
        "regime_rejected": int(summary_dict.get("regime_rejected", 0)),
        "ai_rejected": int(summary_dict.get("ai_rejected", 0)),
    }
    return mapped


def calculate_analytics(trades_df, summary):
    """
    Calculate detailed analytics for the analytics tab
    """
    analytics = {
        "ai_performance": {},
        "risk_metrics": {},
        "cost_analysis": {},
        "trade_distribution": {},
        "performance_stats": {}
    }
    
    if trades_df.empty:
        return analytics
    
    pnl_col = choose_col(trades_df, ["pnl_net", "pnl", "PnL", "pnl_dollars"])
    cat_col = choose_col(trades_df, ["strategy", "category", "type", "signal_type"])  # Fixed: Added 'strategy' to find strategy column
    strategy_col = choose_col(trades_df, ["strategy"])
    
    if not pnl_col:
        return analytics
    
    # ---- AI/ML Performance ----
    total_trades = len(trades_df)
    ai_rejected = summary.get("ai_rejected", 0)
    quality_rejected = summary.get("quality_rejected", 0)
    regime_rejected = summary.get("regime_rejected", 0)
    
    potentials = summary.get("potentials", 0)
    total_signals = potentials + ai_rejected
    
    analytics["ai_performance"] = {
        "total_signals": int(total_signals),
        "ai_rejected": int(ai_rejected),
        "quality_rejected": int(quality_rejected),
        "regime_rejected": int(regime_rejected),
        "ai_approval_rate": float((potentials / total_signals * 100) if total_signals > 0 else 0),
        "trades_executed": int(total_trades),
        "execution_rate": float((total_trades / potentials * 100) if potentials > 0 else 0)
    }
    
    # ---- Risk Metrics ----
    wins = (trades_df[pnl_col] > 0).sum()
    losses = (trades_df[pnl_col] < 0).sum()
    
    win_pnls = trades_df[trades_df[pnl_col] > 0][pnl_col]
    loss_pnls = trades_df[trades_df[pnl_col] < 0][pnl_col]
    
    avg_win = float(win_pnls.mean()) if len(win_pnls) > 0 else 0.0
    avg_loss = float(loss_pnls.mean()) if len(loss_pnls) > 0 else 0.0
    
    profit_factor = abs(win_pnls.sum() / loss_pnls.sum()) if len(loss_pnls) > 0 and loss_pnls.sum() != 0 else 0.0
    
    # Calculate max drawdown
    cum_pnl = trades_df[pnl_col].cumsum()
    running_max = cum_pnl.expanding().max()
    drawdown = cum_pnl - running_max
    max_drawdown = float(drawdown.min()) if len(drawdown) > 0 else 0.0
    
    analytics["risk_metrics"] = {
        "win_rate": float((wins / total_trades * 100) if total_trades > 0 else 0),
        "avg_win": float(avg_win),
        "avg_loss": float(avg_loss),
        "profit_factor": float(profit_factor),
        "max_drawdown": float(max_drawdown),
        "sharpe_ratio": float(calculate_sharpe_ratio(trades_df, pnl_col))
    }
    
    # ---- Cost Analysis ----
    # Assuming 0.1% commission per trade (0.05% entry + 0.05% exit)
    entry_col = choose_col(trades_df, ["entry", "entry_price", "open_price"])
    exit_col = choose_col(trades_df, ["exit", "exit_price", "close_price"])
    
    if entry_col and exit_col:
        total_value = (trades_df[entry_col] + trades_df[exit_col]).sum()
        estimated_commissions = total_value * 0.001  # 0.1% of total trade value
    else:
        estimated_commissions = total_trades * 2.0  # Fallback: $2 per trade
    
    gross_pnl = float(trades_df[pnl_col].sum())
    net_pnl = gross_pnl - estimated_commissions
    
    analytics["cost_analysis"] = {
        "gross_pnl": float(gross_pnl),
        "estimated_commissions": float(estimated_commissions),
        "net_pnl": float(net_pnl),
        "commission_per_trade": float(estimated_commissions / total_trades if total_trades > 0 else 0),
        "cost_to_profit_ratio": float((estimated_commissions / gross_pnl * 100) if gross_pnl > 0 else 0)
    }
    
    # ---- Trade Distribution ----
    if cat_col:
        category_counts = trades_df[cat_col].value_counts().to_dict()
        category_pnl = trades_df.groupby(cat_col)[pnl_col].sum().to_dict()
        
        # Beautify strategy names for display
        strategy_labels = {
            "mean_reversion": "Mean Reversion",
            "price_action": "Price Action",
            "news_pa_confluence": "News+PA Confluence",
            "mr_pa_confluence": "MR+PA Confluence",
            "news": "News/Macro",
            "macro": "News/Macro",
            "earnings": "Earnings/Insider",
            "insider": "Earnings/Insider"
        }
        
        analytics["trade_distribution"] = {
            "by_category": {
                strategy_labels.get(str(k).lower(), str(k).replace('_', ' ').title()): {
                    "count": int(v),
                    "pnl": float(category_pnl.get(k, 0))
                }
                for k, v in category_counts.items()
            }
        }
    
    # ---- Performance Stats ----
    initial_balance = summary.get("initial_balance", 100000.0)
    final_balance = summary.get("final_balance", 100000.0)
    
    analytics["performance_stats"] = {
        "total_return_pct": float(((final_balance - initial_balance) / initial_balance * 100)),
        "total_trades": int(total_trades),
        "winning_trades": int(wins),
        "losing_trades": int(losses),
        "forced_exits": int(summary.get("forced_exits", 0))
    }
    
    return analytics


def calculate_sharpe_ratio(trades_df, pnl_col):
    """Calculate Sharpe Ratio from trade returns"""
    if trades_df.empty or pnl_col not in trades_df.columns:
        return 0.0
    
    returns = trades_df[pnl_col]
    if len(returns) < 2:
        return 0.0
    
    mean_return = returns.mean()
    std_return = returns.std()
    
    if std_return == 0:
        return 0.0
    
    # Annualized Sharpe (assuming 252 trading days)
    sharpe = (mean_return / std_return) * (252 ** 0.5)
    return float(sharpe)


# -----------------------------------------------------------------------------
# Routes - Serve static files
# -----------------------------------------------------------------------------
@app.route("/")
def index():
    dash_path = os.path.join(APP_ROOT, "dashboard.html")
    if os.path.exists(dash_path):
        return send_from_directory(APP_ROOT, "dashboard.html")
    return jsonify({"error": "dashboard.html not found"}), 404


@app.route("/<path:filename>")
def serve_static(filename):
    return send_from_directory(APP_ROOT, filename)


# -----------------------------------------------------------------------------
# Routes - Simple status
# -----------------------------------------------------------------------------
@app.route("/api/status")
def api_status():
    return jsonify({"status": "ok", "message": "Flask backend running"})


# -----------------------------------------------------------------------------
# Routes - Dashboard data
# -----------------------------------------------------------------------------
@app.route("/api/dashboard")
def api_dashboard():
    """Provide dashboard metrics + performance curve + recent trades"""
    summary = load_summary()
    trades_df = load_trades_df()

    metrics = summarize_trades(trades_df, summary)
    performance_data = build_performance_data(trades_df, summary.get("initial_balance", 100000.0))
    recent_trades = map_trades_for_api(trades_df, limit=10)

    return jsonify({
        "portfolio_value": metrics["portfolio_value"],
        "active_trades": metrics["active_trades"],
        "win_rate": metrics["win_rate"],
        "total_pnl": metrics["total_pnl"],
        "performance_data": performance_data,
        "recent_trades": recent_trades,
    })


@app.route("/api/trades")
def api_trades():
    """Return all executed trades"""
    trades_df = load_trades_df()
    trades = map_trades_for_api(trades_df, limit=None)
    return jsonify(trades)


@app.route("/api/analytics")
def api_analytics():
    """
    NEW ENDPOINT: Return detailed analytics for the analytics tab
    """
    summary = load_summary()
    trades_df = load_trades_df()
    
    analytics = calculate_analytics(trades_df, summary)
    
    return jsonify(analytics)


# -----------------------------------------------------------------------------
# Routes - Backtest
# -----------------------------------------------------------------------------
def _run_backtest_in_thread(config):
    """
    Worker function to run backtest in background.
    FIXED: Properly handles ticker list without splitting into characters.
    NEW: Supports custom date ranges
    """
    global backtest_status

    interval = config.get("interval", "15m")
    volume_threshold = float(config.get("volume_threshold", 1.5))
    enable_ai = bool(config.get("enable_ai", True))
    enable_ml = bool(config.get("enable_ml", True))
    enable_earnings = bool(config.get("enable_earnings", True))
    
    # ✨ NEW: Accept stop loss and profit target from dashboard
    profit_target_pct = config.get("profit_target")  # From dashboard (already as decimal)
    stop_loss_pct = config.get("stop_loss")          # From dashboard (already as decimal)

    print("[API] Starting backtest from app.py")
    print(f"  interval={interval}, volume_threshold={volume_threshold}")
    print(f"  enable_ai={enable_ai}, enable_ml={enable_ml}, enable_earnings={enable_earnings}")
    if profit_target_pct is not None:
        print(f"  profit_target={profit_target_pct*100:.1f}%, stop_loss={stop_loss_pct*100:.1f}%")

    try:
        ensure_outputs_dir()

        # ✅ NEW: Support custom date ranges
        use_custom_dates = config.get("use_custom_dates", False)
        
        if use_custom_dates:
            # Custom date range mode
            start_str = config.get("start_date", "")
            end_str = config.get("end_date", "")
            
            if start_str:
                try:
                    start_date = datetime.strptime(start_str, "%Y-%m-%d")
                    print(f"[API] Using custom start date: {start_date.date()}")
                except ValueError:
                    print(f"[API] Invalid start date format, using default")
                    use_custom_dates = False
            else:
                use_custom_dates = False
            
            if end_str and use_custom_dates:
                try:
                    end_date = datetime.strptime(end_str, "%Y-%m-%d")
                    print(f"[API] Using custom end date: {end_date.date()}")
                except ValueError:
                    print(f"[API] Invalid end date format, using today")
                    end_date = datetime.now()
            elif use_custom_dates:
                end_date = datetime.now()
                print(f"[API] Using current date as end: {end_date.date()}")
        
        if not use_custom_dates:
            # Lookback days mode (default)
            lookback_days = int(config.get("lookback_days", 30))
            print(f"[API] Using lookback mode: {lookback_days} days")
            end_date = datetime.now()
            start_date = end_date - timedelta(days=lookback_days)

        # ✅ FIX: Default ticker universe (configurable via frontend later)
        default_tickers = [
            "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA",
            "AMD", "NFLX", "INTC", "CRM", "ADBE", "CSCO", "ORCL"
        ]
        tickers = config.get("tickers", default_tickers)
        
        # ✅ CRITICAL FIX: Ensure tickers is a list, not a string
        if isinstance(tickers, str):
            # If it's a comma-separated string, split it
            tickers = [t.strip() for t in tickers.split(",") if t.strip()]
        elif not isinstance(tickers, list):
            tickers = default_tickers

        print(f"[API] Date range: {start_date.date()} to {end_date.date()}")
        print(f"[API] Tickers ({len(tickers)}): {', '.join(tickers[:5])}{'...' if len(tickers) > 5 else ''}")
        print(f"[API] Ticker type: {type(tickers)}, First ticker: {tickers[0] if tickers else 'None'}")

        # ✅ FIX: Build complete arguments
        kwargs = {
            "start": start_date,
            "end": end_date,
            "interval": interval,
            "tickers": tickers,
            "volume_threshold": volume_threshold,
            "enable_ai": enable_ai,
            "enable_ml": enable_ml,
            "enable_earnings": enable_earnings,
            "enable_quality_filter": True,
            "export_dir": OUTPUT_DIR,
        }
        
        # ✨ NEW: Add stop loss / profit target if provided by dashboard
        if profit_target_pct is not None:
            kwargs["profit_target_pct"] = float(profit_target_pct)
        if stop_loss_pct is not None:
            kwargs["stop_loss_pct"] = float(stop_loss_pct)

        print(f"[API] Calling run_backtest with {len(kwargs)} parameters")
        result = run_backtest(**kwargs)

        # --- Normalize result shape ---
        final_trades = []
        summary = {}
        ai_report = {}

        if isinstance(result, tuple):
            if len(result) == 3:
                final_trades, summary, ai_report = result
            elif len(result) == 2:
                final_trades, summary = result
            elif len(result) == 1:
                summary = result[0]
        elif isinstance(result, dict):
            summary = result

        mapped_summary = map_summary_for_frontend(summary)

        with backtest_lock:
            backtest_status["status"] = "completed"
            backtest_status["progress"] = 100
            backtest_status["error"] = None
            backtest_status["results"] = {
                "summary": mapped_summary,
                "ai_report": ai_report if ai_report is not None else {},
            }

        print("\n[API] ✅ Backtest completed successfully!")
        print("="*60)
        print(f"[API] Period: {summary.get('period_start', 'N/A')} → {summary.get('period_end', 'N/A')}")
        print(f"[API] Initial Balance: ${mapped_summary.get('initial_balance', 100000):.2f}")
        print(f"[API] Final Balance:   ${mapped_summary.get('final_balance', 100000):.2f}")
        print(f"[API] Total P&L:       ${mapped_summary.get('total_pl', 0):.2f}")
        print(f"[API] Return:          {mapped_summary.get('return_pct', 0):.2f}%")
        print(f"[API] Trades Executed: {mapped_summary.get('trades', 0)}")
        
        # ✨ FIXED: Show ALL strategies, not just news categories
        news_count = mapped_summary.get('news_trades', 0)
        earnings_count = mapped_summary.get('earnings_trades', 0)
        mr_count = mapped_summary.get('mean_reversion_trades', 0)
        
        print(f"[API] Strategy Breakdown:")
        print(f"[API]   News/Macro: {news_count} trades")
        print(f"[API]   Earnings/Insider: {earnings_count} trades")
        print(f"[API]   Mean Reversion: {mr_count} trades")
        print("="*60)

    except Exception as e:
        print(f"[API] ❌ Backtest FAILED: {e}")
        import traceback
        traceback.print_exc()
        
        with backtest_lock:
            backtest_status["status"] = "error"
            backtest_status["progress"] = 0
            backtest_status["error"] = str(e)
            backtest_status["results"] = None
    finally:
        with backtest_lock:
            backtest_status["is_running"] = False


@app.route("/api/backtest", methods=["POST"])
def api_backtest():
    """
    Start a backtest in the background.
    Frontend sends JSON like:
      {
        interval: "15m",
        lookback_days: 30,
        volume_threshold: 1.5,
        enable_ai: true,
        enable_ml: true,
        enable_earnings: true
      }
    """
    global backtest_status

    with backtest_lock:
        if backtest_status["is_running"]:
            return jsonify({"error": "Backtest already running"}), 400

        config = request.get_json(silent=True) or {}

        backtest_status = {
            "is_running": True,
            "status": "running",
            "progress": 0,
            "error": None,
            "results": None,
        }

        t = threading.Thread(target=_run_backtest_in_thread, args=(config,), daemon=True)
        t.start()

    return jsonify({"message": "Backtest started"}), 200


@app.route("/api/backtest/status")
def api_backtest_status():
    """Return current backtest status + results"""
    with backtest_lock:
        return jsonify(backtest_status)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    ensure_outputs_dir()

    dash_path = os.path.join(APP_ROOT, "dashboard.html")
    print("=" * 60)
    print("AI Trading System - Flask Backend")
    print(f"Outputs directory: {OUTPUT_DIR}")
    if not os.path.exists(dash_path):
        print("WARNING: dashboard.html not found in project root.")
        print("Place your dashboard.html alongside app.py")
        print()
        print("API is still available:")
        print("  GET  /api/status")
        print("  POST /api/backtest")
        print("  GET  /api/backtest/status")
        print("  GET  /api/dashboard")
        print("  GET  /api/trades")
        print("  GET  /api/analytics  [NEW]")
    else:
        print("✓ dashboard.html found.")
        print("Open http://localhost:5000 in your browser.")
    print("=" * 60)

    app.run(debug=True, host="0.0.0.0", port=5000, threaded=True)