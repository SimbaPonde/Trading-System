"""
runmodes/backtest.py - Wrapper for unified_backtest.py to work with Flask API
"""

import os
import sys
import json
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path so we can import unified_backtest
sys.path.insert(0, str(Path(__file__).parent.parent))

from unified_backtest import UnifiedBacktest


def run_backtest(
    start=None,
    end=None,
    interval="1d",
    tickers=None,
    volume_threshold=1.5,
    enable_ai=True,
    enable_ml=True,
    enable_earnings=True,
    enable_quality_filter=True,
    export_dir="outputs",
    **kwargs
):
    """
    Run backtest compatible with Flask API
    
    Args:
        start: Start datetime
        end: End datetime
        interval: Trading interval (1d, 4h, 1h, 30m, 15m, 5m, 1m)
        tickers: List of ticker symbols
        volume_threshold: Volume threshold (not used but kept for compatibility)
        enable_ai: Enable AI features (not used but kept for compatibility)
        enable_ml: Enable ML features (not used but kept for compatibility)
        enable_earnings: Enable earnings strategy
        enable_quality_filter: Enable quality filter (not used but kept for compatibility)
        export_dir: Output directory
        **kwargs: Additional arguments
    
    Returns:
        tuple: (trades_list, summary_dict, ai_report_dict)
    """
    
    # Handle 4h interval (yfinance doesn't support it directly)
    # Download 1h data and resample to 4h
    actual_interval = interval
    needs_resampling = False
    if interval == "4h":
        actual_interval = "1h"
        needs_resampling = True
        print("[WRAPPER] Converting 4h to 1h with resampling")
    
    print("[WRAPPER] Starting unified backtest...")
    print(f"[WRAPPER] Date range: {start.date()} to {end.date()}")
    print(f"[WRAPPER] Interval: {interval}")
    print(f"[WRAPPER] Tickers: {len(tickers)} symbols")
    
    # ✨ NEW: Extract stop loss / profit target if provided
    profit_target_pct = kwargs.get("profit_target_pct")
    stop_loss_pct = kwargs.get("stop_loss_pct")
    if profit_target_pct is not None or stop_loss_pct is not None:
        print(f"[WRAPPER] Custom parameters: profit_target={profit_target_pct*100 if profit_target_pct else 'default'}%, stop_loss={stop_loss_pct*100 if stop_loss_pct else 'default'}%")
    
    # Ensure start/end are timezone-naive for consistency
    if hasattr(start, 'tzinfo') and start.tzinfo is not None:
        start = start.replace(tzinfo=None)
    if hasattr(end, 'tzinfo') and end.tzinfo is not None:
        end = end.replace(tzinfo=None)
    
    try:
        # Create unified backtest instance (only takes config_path!)
        backtest = UnifiedBacktest(config_path="config/config.yaml")
        
        # ✨ NEW: Set custom profit/stop as instance attributes for mean reversion
        if profit_target_pct is not None:
            backtest._custom_profit_target = float(profit_target_pct)
            print(f"[WRAPPER] Custom profit target: {profit_target_pct*100:.1f}%")
        if stop_loss_pct is not None:
            backtest._custom_stop_loss = float(stop_loss_pct)
            print(f"[WRAPPER] Custom stop loss: {stop_loss_pct*100:.1f}%")
        
        # Run strategies with tickers passed directly to methods
        print("[WRAPPER] Running News/Macro strategy...")
        backtest.news_trades = backtest.run_news_macro_strategy(
            tickers=tickers,
            start=start,
            end=end,
            interval=actual_interval,
            price_cache="price_cache"
        )
        
        print("[WRAPPER] Running Earnings/Insider strategy...")
        backtest.earnings_trades = backtest.run_earnings_insider_strategy(
            tickers=tickers,
            start=start,
            end=end,
            sec_user_agent="Automated Trading System trading@system.com",
            cache_dir="cache"
        )
        
        print("[WRAPPER] Running Mean Reversion strategy...")
        backtest.mean_reversion_trades = backtest.run_mean_reversion_strategy(
            tickers=tickers,
            start=start,
            end=end,
            interval=actual_interval,
            asset_type="stocks"
        )
        
        # NEW: Get prices dict from news strategy for other strategies to use
        # Re-use the prices that were loaded in news/macro strategy
        from data.news_data.prices import PriceConfig, load_history
        price_cfg = PriceConfig(cache_dir="price_cache")
        prices = {}
        
        start_utc = pd.to_datetime(start)
        end_utc = pd.to_datetime(end)
        if start_utc.tzinfo is None:
            start_utc = start_utc.tz_localize('UTC')
        if end_utc.tzinfo is None:
            end_utc = end_utc.tz_localize('UTC')
        
        for t in tickers:
            try:
                df = load_history(
                    t,
                    interval=actual_interval,
                    start=start_utc,
                    end=end_utc,
                    cfg=price_cfg
                )
                
                # Resample to 4h if needed
                if needs_resampling and not df.empty:
                    df = df.resample('4h').agg({
                        'Open': 'first',
                        'High': 'max',
                        'Low': 'min',
                        'Close': 'last',
                        'Volume': 'sum'
                    }).dropna()
                
                prices[t] = df
            except Exception:
                continue
        
        # NEW: Run Price Action strategy
        print("[WRAPPER] Running Price Action strategy...")
        backtest.price_action_trades = backtest.run_price_action_strategy(
            tickers=tickers,
            start=start,
            end=end,
            prices=prices
        )
        
        # NEW: Get news for News+PA confluence
        from data.news_data.news import NewsConfig, fetch_news
        news_cfg = NewsConfig(use_finnhub=backtest.config["news"]["use_finnhub"])
        news = fetch_news(tickers, start=start, end=end, cfg=news_cfg)
        
        # NEW: Run News + PA Confluence strategy
        print("[WRAPPER] Running News + Price Action Confluence...")
        backtest.news_pa_confluence_trades = backtest.run_news_pa_confluence_strategy(
            tickers=tickers,
            start=start,
            end=end,
            prices=prices,
            news_df=news
        )
        
        # NEW: Get MR signals for MR+PA confluence
        from strategies.mean_reversion_strategy.mean_reversion import MeanReversionStrategy
        from strategies.mean_reversion_strategy.config.config import MeanReversionParams, AssetClass
        
        mr_params = MeanReversionParams(
            bb_period=backtest.config['mean_reversion']['lookback_period'],  # Fixed: 'lookback_period' not 'bb_period'
            bb_std_dev=backtest.config['mean_reversion']['bollinger_std'],  # Fixed: 'bollinger_std' not 'bb_std_dev'
            rsi_period=backtest.config['mean_reversion']['rsi_period'],
            rsi_oversold=backtest.config['mean_reversion']['rsi_oversold'],
            rsi_overbought=backtest.config['mean_reversion']['rsi_overbought']
        )
        
        mr_strategy_obj = MeanReversionStrategy(mr_params, AssetClass.STOCK)
        
        mr_signals = []
        for ticker in tickers:
            if ticker not in prices:
                continue
            signals = mr_strategy_obj.generate_signals(prices[ticker], ticker)
            for sig in signals:
                mr_signals.append({
                    'ticker': sig.ticker,
                    'entry_time': sig.time,
                    'side': sig.side,
                    'entry_price': sig.price,
                    'stop_loss': sig.stop_loss,
                    'take_profit': sig.take_profit,
                    'confidence': sig.confidence,
                    'reason': sig.reason,
                    'rsi': sig.indicators.get('rsi') if hasattr(sig, 'indicators') else None,
                    'bb_position': sig.indicators.get('bb_position') if hasattr(sig, 'indicators') else None,
                    'zscore': sig.indicators.get('zscore') if hasattr(sig, 'indicators') else None
                })
        
        mr_signals_df = pd.DataFrame(mr_signals) if mr_signals else pd.DataFrame()
        
        # NEW: Run MR + PA Confluence strategy
        print("[WRAPPER] Running MR + Price Action Confluence...")
        backtest.mr_pa_confluence_trades = backtest.run_mr_pa_confluence_strategy(
            tickers=tickers,
            start=start,
            end=end,
            prices=prices,
            mr_signals=mr_signals_df
        )
        
        # Combine results
        print("[WRAPPER] Combining results...")
        backtest.all_trades = backtest.combine_results()
        
        # Get summary statistics
        stats = backtest.generate_summary()
        
        # Save outputs
        print(f"[WRAPPER] Saving to {export_dir}...")
        os.makedirs(export_dir, exist_ok=True)
        
        # Save unified trades
        if not backtest.all_trades.empty:
            trades_path = os.path.join(export_dir, "trades.csv")
            backtest.all_trades.to_csv(trades_path, index=False)
            print(f"[WRAPPER] Saved {len(backtest.all_trades)} trades to {trades_path}")
        
        # Save summary as summary.json (for Flask API compatibility)
        summary_path = os.path.join(export_dir, "summary.json")
        
        # Build summary for Flask
        initial_balance = float(backtest.config["trading"]["initial_balance"])
        
        # Calculate totals (use .get() to handle missing strategies)
        news_pnl = stats["strategies"].get("news_macro", {}).get("total_pnl", 0.0)
        earnings_pnl = stats["strategies"].get("earnings_insider", {}).get("total_pnl", 0.0)
        mean_rev_pnl = stats["strategies"].get("mean_reversion", {}).get("total_pnl", 0.0)
        
        # NEW: Add PnL from new strategies
        pa_pnl = stats["strategies"].get("price_action", {}).get("total_pnl", 0.0)
        news_pa_pnl = stats["strategies"].get("news_pa_confluence", {}).get("total_pnl", 0.0)
        mr_pa_pnl = stats["strategies"].get("mr_pa_confluence", {}).get("total_pnl", 0.0)
        
        total_pnl = news_pnl + earnings_pnl + mean_rev_pnl + pa_pnl + news_pa_pnl + mr_pa_pnl
        
        final_balance = initial_balance + total_pnl
        return_pct = (total_pnl / initial_balance) * 100 if initial_balance > 0 else 0.0
        
        summary = {
            "initial_balance": initial_balance,
            "final_balance": final_balance,
            "pnl": total_pnl,
            "return_pct": return_pct,
            "trades_executed": stats["total_trades"],
            "period_start": start.strftime("%Y-%m-%d"),
            "period_end": end.strftime("%Y-%m-%d"),
            "interval": interval,
            
            # Strategy breakdown
            "news_trades": stats["strategies"].get("news_macro", {}).get("trades", 0),
            "macro_trades": 0,  # Combined with news
            "confluence_trades": 0,  # Combined with news
            "earnings_trades": stats["strategies"].get("earnings_insider", {}).get("trades", 0),
            "mean_reversion_trades": stats["strategies"].get("mean_reversion", {}).get("trades", 0),
            
            # NEW: Add new strategy counts
            "price_action_trades": stats["strategies"].get("price_action", {}).get("trades", 0),
            "news_pa_confluence_trades": stats["strategies"].get("news_pa_confluence", {}).get("trades", 0),
            "mr_pa_confluence_trades": stats["strategies"].get("mr_pa_confluence", {}).get("trades", 0),
            
            # Event statistics
            "news_events": stats["event_stats"]["news_events"],
            "macro_events": stats["event_stats"]["macro_events"],
            "earnings_events": stats["event_stats"]["earnings_events"],
            "blackout_hours": stats["event_stats"]["blackout_hours"],
            
            # Additional fields for compatibility
            "forced_exits": 0,
            "potentials": 0,
            "risk_regime": "NEUTRAL",
            "quality_rejected": 0,
            "regime_rejected": 0,
            "ai_rejected": 0,
        }
        
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2)
        
        print(f"[WRAPPER] Saved summary to {summary_path}")
        print(f"[WRAPPER] Backtest complete: {stats['total_trades']} trades, ${total_pnl:.2f} P&L")
        
        # Print detailed breakdown
        print("\n[API] ✅ Backtest completed successfully!")
        print("="*60)
        print(f"[API] Period: {start.date()} → {end.date()}")
        print(f"[API] Initial Balance: ${initial_balance:,.2f}")
        print(f"[API] Final Balance:   ${final_balance:,.2f}")
        print(f"[API] Total P&L:       ${total_pnl:,.2f}")
        print(f"[API] Return:          {return_pct:.2f}%")
        print(f"[API] Trades Executed: {stats['total_trades']}")
        print(f"[API] Strategy Breakdown:")
        print(f"[API]   News/Macro: {stats['strategies'].get('news_macro', {}).get('trades', 0)} trades")
        print(f"[API]   Earnings/Insider: {stats['strategies'].get('earnings_insider', {}).get('trades', 0)} trades")
        print(f"[API]   Mean Reversion: {stats['strategies'].get('mean_reversion', {}).get('trades', 0)} trades")
        print(f"[API]   Price Action: {stats['strategies'].get('price_action', {}).get('trades', 0)} trades")
        print(f"[API]   News+PA Confluence: {stats['strategies'].get('news_pa_confluence', {}).get('trades', 0)} trades")
        print(f"[API]   MR+PA Confluence: {stats['strategies'].get('mr_pa_confluence', {}).get('trades', 0)} trades")
        
        # Return in Flask-compatible format
        return ([], summary, {})
        
    except Exception as e:
        print(f"[WRAPPER] ERROR: {e}")
        import traceback
        traceback.print_exc()
        
        # Return error summary
        return ([], {
            "initial_balance": 100000.0,
            "final_balance": 100000.0,
            "pnl": 0.0,
            "return_pct": 0.0,
            "trades_executed": 0,
            "error": str(e)
        }, {})
