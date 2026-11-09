"""
Unified Backtest Runner
Integrates News/Macro, Earnings/Insider, and Mean Reversion strategies
with intelligent event coordination
"""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List
import pandas as pd
import yaml
from dotenv import load_dotenv

# Import event coordinator
from strategies.event_coordinator import EventCoordinator


class UnifiedBacktest:
    """
    Unified backtest engine that runs all three strategies independently
    with event coordination for mean reversion blackouts
    """
    
    def __init__(self, config_path: str = "config/config.yaml"):
        """Initialize with configuration"""
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
            
        self.event_coordinator = EventCoordinator(
            blackout_hours=self.config['mean_reversion']['event_blackout_hours']
        )
        
        # Storage for strategy results
        self.news_trades: pd.DataFrame = pd.DataFrame()
        self.earnings_trades: pd.DataFrame = pd.DataFrame()
        self.mean_reversion_trades: pd.DataFrame = pd.DataFrame()
        
        # NEW: Storage for new strategies
        self.price_action_trades: pd.DataFrame = pd.DataFrame()
        self.news_pa_confluence_trades: pd.DataFrame = pd.DataFrame()
        self.mr_pa_confluence_trades: pd.DataFrame = pd.DataFrame()
        
        # Combined results
        self.all_trades: pd.DataFrame = pd.DataFrame()
        
    def run_news_macro_strategy(
        self,
        tickers: List[str],
        start: datetime,
        end: datetime,
        interval: str = "1d",
        price_cache: str = "price_cache"
    ) -> pd.DataFrame:
        """
        Run news/macro strategy
        """
        print("\n" + "="*60)
        print("RUNNING NEWS/MACRO STRATEGY")
        print("="*60)
        
        # Import locally to avoid circular imports
        from utils.io import read_tickers_file
        from data.news_data.prices import PriceConfig, load_history
        from data.news_data.news import NewsConfig, fetch_news
        from data.news_data.macros import MacroConfig, fetch_macros
        from strategies.news_strategy.integrated_signals import (
            generate_integrated_signals, filter_by_grade, MACRO_ETFS
        )
        from strategies.news_strategy.exits import ExitConfig, simulate_exits
        from strategies.news_strategy.costs import CostConfig, apply_costs
        
        # Load prices
        price_cfg = PriceConfig(cache_dir=price_cache)
        prices = {}
        
        # Normalize start/end to UTC-aware for price loading (prices.py expects UTC)
        start_utc = pd.Timestamp(start)
        end_utc = pd.Timestamp(end)
        if start_utc.tzinfo is None:
            start_utc = start_utc.tz_localize('UTC')
        if end_utc.tzinfo is None:
            end_utc = end_utc.tz_localize('UTC')
        
        for t in tickers:
            try:
                print(f"  Loading {t}...")
                prices[t] = load_history(
                    t,
                    interval=interval,
                    start=start_utc,
                    end=end_utc,
                    cfg=price_cfg
                )
            except Exception as e:
                print(f"  ✗ {t} failed: {str(e)}")
                continue
                
        # Fetch news
        news_cfg = NewsConfig(use_finnhub=self.config["news"]["use_finnhub"])
        news = fetch_news(tickers, start=start, end=end, cfg=news_cfg)
        if not news.empty:
            # Normalize start/end for comparison (handle timezone-aware vs naive)
            start_ts = pd.to_datetime(start)
            end_ts = pd.to_datetime(end)
            
            # If news timestamps are tz-aware and start/end are not, make them aware
            if hasattr(news["timestamp"].dtype, 'tz') and news["timestamp"].dt.tz is not None:
                if start_ts.tzinfo is None:
                    start_ts = start_ts.tz_localize('UTC')
                if end_ts.tzinfo is None:
                    end_ts = end_ts.tz_localize('UTC')
            # If news timestamps are tz-naive and start/end are aware, make them naive
            elif start_ts.tzinfo is not None:
                start_ts = start_ts.tz_localize(None)
                end_ts = end_ts.tz_localize(None)
                
            news = news[
                (news["timestamp"] >= start_ts) &
                (news["timestamp"] <= end_ts)
            ].copy()
            
        # Fetch macros
        macro_cfg = MacroConfig(
            include_event_types=self.config["macros"]["include_event_types"],
            redundant_sources=self.config["macros"]["redundant_sources"],
        )
        macros = fetch_macros(start=start, end=end, cfg=macro_cfg)
        if not macros.empty:
            # Normalize start/end for comparison (handle timezone-aware vs naive)
            start_ts = pd.to_datetime(start)
            end_ts = pd.to_datetime(end)
            
            # If macro timestamps are tz-aware and start/end are not, make them aware
            if hasattr(macros["timestamp"].dtype, 'tz') and macros["timestamp"].dt.tz is not None:
                if start_ts.tzinfo is None:
                    start_ts = start_ts.tz_localize('UTC')
                if end_ts.tzinfo is None:
                    end_ts = end_ts.tz_localize('UTC')
            # If macro timestamps are tz-naive and start/end are aware, make them naive
            elif start_ts.tzinfo is not None:
                start_ts = start_ts.tz_localize(None)
                end_ts = end_ts.tz_localize(None)
                
            macros = macros[
                (macros["timestamp"] >= start_ts) &
                (macros["timestamp"] <= end_ts)
            ].copy()
            
        # Register events with coordinator
        self.event_coordinator.register_events(news_df=news, macro_df=macros)
        
        # Generate signals
        all_signals = []
        for ticker, df in prices.items():
            if df.empty:
                continue
                
            is_etf = ticker in MACRO_ETFS
            ticker_signals = generate_integrated_signals(
                df=df,
                news_df=news,
                macro_df=macros,
                ticker=ticker,
                interval=interval,
                is_etf=is_etf
            )
            
            ticker_signals = filter_by_grade(ticker_signals, min_grade='A')
            all_signals.extend(ticker_signals)
            
        print(f"  Generated {len(all_signals)} signals")
        
        # Convert to trades
        trades = []
        initial_balance = float(self.config["trading"]["initial_balance"])
        risk_per_trade = float(self.config["trading"]["risk_per_trade"])
        max_pos_pct = float(self.config["trading"]["max_position_pct"])
        
        for signal in all_signals:
            ticker = signal.get('ticker')
            price = signal.get('price')
            stop_dist = signal.get('stop_dist', 0)
            side = signal.get('side', signal.get('type', 'BUY'))
            
            if stop_dist and stop_dist > 0:
                risk_amount = initial_balance * risk_per_trade
                size = int(max(10, risk_amount / stop_dist))
                max_shares = int((initial_balance * max_pos_pct) / price)
                size = int(max(10, min(size, max_shares)))
            else:
                size = int(max(10, (initial_balance * 0.05) / price))
                
            trades.append({
                "ticker": ticker,
                "entry_time": signal.get('time'),
                "entry_price": price,
                "side": side,
                "strategy": "news_macro",
                "category": signal.get('category', 'News'),
                "reason": signal.get('reason', 'SIGNAL'),
                "size": size,
                "stop_dist": stop_dist if stop_dist > 0 else price * 0.02,
                "profit_target": signal.get('profit_target', price * 1.05 if side == 'BUY' else price * 0.95),
                "time_exit_bars": signal.get('time_exit_bars', 20),
            })
            
        trades_df = pd.DataFrame(trades)
        
        # Simulate exits
        if not trades_df.empty:
            exit_cfg = ExitConfig(**self.config["exits"])
            trades_df = simulate_exits(trades_df, prices, exit_cfg)
            
            # Apply costs
            cost_cfg = CostConfig(
                commission_rate=float(self.config["trading"]["commission_rate"]),
                slippage_rate=float(self.config["trading"]["slippage_rate"]),
            )
            trades_df = apply_costs(trades_df, cost_cfg)
            
        print(f"  Completed {len(trades_df)} trades")
        return trades_df
        
    def run_earnings_insider_strategy(
        self,
        tickers: List[str],
        start: datetime,
        end: datetime,
        sec_user_agent: str,
        cache_dir: str = "cache"
    ) -> pd.DataFrame:
        """
        Run earnings/insider strategy
        """
        print("\n" + "="*60)
        print("RUNNING EARNINGS/INSIDER STRATEGY")
        print("="*60)
        
        from tqdm import tqdm
        from data.earnings_data.price_loader import load_daily_prices
        from data.earnings_data.earnings_source import get_earnings_events
        from data.earnings_data.sec_form4_source import SECForm4Source
        from data.earnings_data.fundamentals import get_fundamentals_snapshot
        from strategies.earnings_strategy.earnings_insider_strategy import (
            StrategyConfig, score_signals, generate_trade_list
        )
        
        # Load prices
        print("  Loading prices...")
        price_res = load_daily_prices(tickers, start, end, cache_dir=cache_dir, use_cache=True)
        prices_daily = price_res.prices
        
        # Load earnings
        print("  Loading earnings...")
        earnings_frames = []
        for t in tqdm(tickers, desc="  Earnings"):
            df = get_earnings_events(t, start, end)
            if df is not None and not df.empty:
                earnings_frames.append(df)
        earnings_df = pd.concat(earnings_frames, ignore_index=True) if earnings_frames else pd.DataFrame()
        
        # Register earnings events with coordinator
        self.event_coordinator.register_events(earnings_df=earnings_df)
        
        # Load insider trades
        print("  Loading SEC Form 4...")
        sec = SECForm4Source(user_agent=sec_user_agent, cache_dir=cache_dir)
        insider_frames = []
        for t in tqdm(tickers, desc="  SEC Form 4"):
            df = sec.get_insider_trades(t, start, end)
            if df is not None and not df.empty:
                insider_frames.append(df)
        insider_df = pd.concat(insider_frames, ignore_index=True) if insider_frames else pd.DataFrame()
        
        # Load fundamentals
        print("  Loading fundamentals...")
        fund_rows = []
        for t in tickers:
            px = prices_daily.get(t)
            last_close = None
            if px is not None and not px.empty and "Close" in px.columns:
                last_close = float(px["Close"].dropna().iloc[-1])
            snap = get_fundamentals_snapshot(t, last_price=last_close)
            snap["symbol"] = t
            fund_rows.append(snap)
        fundamentals_df = pd.DataFrame(fund_rows) if fund_rows else pd.DataFrame()
        
        # Score signals
        cfg = StrategyConfig(
            min_conviction=self.config['earnings']['min_conviction'],
            max_new_positions_per_day=self.config['earnings']['max_new_positions_per_day'],
            stop_loss_pct=self.config['earnings']['stop_loss_pct'],
            take_profit_pct=self.config['earnings']['take_profit_pct'],
            max_holding_days=self.config['earnings']['max_holding_days'],
            mode="earnings_insider",
        )
        
        scored = score_signals(prices_daily, earnings_df, insider_df, fundamentals_df, cfg)
        trade_list = generate_trade_list(prices_daily, scored, cfg)
        
        # Convert to DataFrame
        trades_df = pd.DataFrame(trade_list)
        if not trades_df.empty:
            trades_df['strategy'] = 'earnings_insider'
            
        print(f"  Generated {len(trades_df)} trade signals")
        return trades_df
        
    def run_mean_reversion_strategy(
        self,
        tickers: List[str],
        start: datetime,
        end: datetime,
        interval: str = "1d",
        asset_type: str = "stocks"
    ) -> pd.DataFrame:
        """
        Run mean reversion strategy with event blackout
        """
        print("\n" + "="*60)
        print("RUNNING MEAN REVERSION STRATEGY (with event blackout)")
        print("="*60)
        
        import yfinance as yf
        from strategies.mean_reversion_strategy.mean_reversion import MeanReversionStrategy
        from strategies.mean_reversion_strategy.config.config import (
            MeanReversionParams, AssetClass
        )
        
        # Load prices
        print("  Loading prices...")
        
        # Handle 4h interval (yfinance doesn't support it)
        actual_interval = interval
        needs_resampling = False
        if interval == "4h":
            actual_interval = "1h"
            needs_resampling = True
        
        prices = {}
        for sym in tickers:
            df = yf.download(
                sym,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                interval=actual_interval,
                auto_adjust=True,
                progress=False
            )
            
            if df is None or df.empty:
                continue
                
            # Flatten multiindex if needed
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df.rename(columns=str.title)
            
            # Handle duplicates
            for col in ["Open", "High", "Low", "Close", "Volume"]:
                if col in df.columns and isinstance(df[col], pd.DataFrame):
                    df[col] = df[col].iloc[:, 0]
            
            # Resample to 4h if needed
            if needs_resampling:
                df = df.resample('4h').agg({
                    'Open': 'first',
                    'High': 'max',
                    'Low': 'min',
                    'Close': 'last',
                    'Volume': 'sum'
                }).dropna()
                    
            df = df.dropna()
            required = {"Open", "High", "Low", "Close"}
            if required.issubset(df.columns):
                prices[sym] = df
                
        # Map asset type
        asset_class = {
            "stocks": AssetClass.STOCK,
            "forex": AssetClass.FOREX,
            "crypto": AssetClass.CRYPTO,
        }.get(asset_type, AssetClass.STOCK)
        
        # Create strategy with config params
        params = MeanReversionParams()
        # ✅ FIX: Use correct attribute names from MeanReversionParams class
        params.bb_period = self.config['mean_reversion']['lookback_period']
        params.bb_std_dev = self.config['mean_reversion']['bollinger_std']
        params.rsi_period = self.config['mean_reversion']['rsi_period']
        params.rsi_oversold = self.config['mean_reversion']['rsi_oversold']
        params.rsi_overbought = self.config['mean_reversion']['rsi_overbought']
        params.zscore_entry = self.config['mean_reversion']['z_score_threshold']
        params.stop_loss_atr_multiplier = self.config['mean_reversion']['atr_multiplier']
        params.position_risk_pct = self.config['mean_reversion']['position_risk_pct']
        
        # ✨ NEW: Override profit target and stop loss if provided from dashboard
        if hasattr(self, '_custom_profit_target'):
            # Convert percentage to multiplier (e.g., 5% profit = 1.5x multiplier if using 2 ATR stop)
            params.profit_target_multiplier = self._custom_profit_target / (params.stop_loss_atr_multiplier * 0.02)  # Rough estimate
        if hasattr(self, '_custom_stop_loss'):
            # Convert percentage to ATR multiplier (e.g., 3% = 1.5 ATR if typical stock ATR is 2%)
            params.stop_loss_atr_multiplier = self._custom_stop_loss / 0.02  # Rough estimate
        
        strategy = MeanReversionStrategy(params=params, asset_class=asset_class)
        
        # Generate signals for all tickers
        all_trades = []
        for ticker, df in prices.items():
            if df.empty:
                continue
                
            signals = strategy.generate_signals(df, ticker=ticker)
            
            # Filter out signals in blackout periods
            filtered_signals = []
            for signal in signals:
                if self.event_coordinator.is_blackout_period(signal.time, ticker):
                    reason = self.event_coordinator.get_blackout_reason(signal.time, ticker)
                    print(f"  ✗ Filtered {ticker} signal at {signal.time}: {reason}")
                else:
                    filtered_signals.append(signal)
                    
            # Convert to trades
            initial_balance = float(self.config["trading"]["initial_balance"])
            risk_pct = float(self.config["mean_reversion"]["position_risk_pct"])
            
            for signal in filtered_signals:
                risk_amount = initial_balance * risk_pct
                stop_dist = abs(float(signal.price) - float(signal.stop_loss))
                if stop_dist <= 0:
                    continue
                
                # Calculate size based on risk
                size = risk_amount / stop_dist
                
                # 🔧 FIX: Add maximum position size limit for forex/crypto
                # Limit to 10% of account balance to prevent massive positions
                max_position_value = initial_balance * 0.10  # Max 10% of account per position
                max_size = max_position_value / float(signal.price)
                
                # Use the smaller of risk-based size or max position size
                original_size = size
                size = min(size, max_size)
                
                # 🔴 ULTRA-CONSERVATIVE MODE: Cap to 5% for stocks only
                # Check ticker suffix to identify asset class, not price
                ticker = signal.ticker
                if not (ticker.endswith('=X') or ticker.endswith('-USD') or ticker.endswith('-USDT')):
                    # This is a stock (not forex or crypto)
                    ultra_conservative_max = (initial_balance * 0.05) / float(signal.price)
                    if size > ultra_conservative_max:
                        print(f"  ⚠️ STOCK POSITION TOO LARGE! {ticker}: {size:.0f} → {ultra_conservative_max:.0f} shares")
                        size = ultra_conservative_max
                
                # DEBUG: Print when position is capped
                if size < original_size * 0.99:  # More than 1% reduction
                    position_value = size * float(signal.price)
                    print(f"  ✅ [CAPPED] {ticker}: {original_size:.0f} → {size:.0f} units (${position_value:,.0f} position)")
                
                all_trades.append({
                    "ticker": signal.ticker,
                    "entry_time": signal.time,
                    "entry_price": float(signal.price),
                    "side": signal.side,
                    "strategy": "mean_reversion",
                    "reason": signal.reason,
                    "stop_loss": float(signal.stop_loss),
                    "take_profit": float(signal.take_profit),
                    "size": float(size),
                    "stop_dist": stop_dist,  # Needed for exit simulation
                })
                
        trades_df = pd.DataFrame(all_trades)
        
        # Simulate exits (like news/macro strategy)
        if not trades_df.empty:
            from strategies.news_strategy.exits import ExitConfig, simulate_exits
            from strategies.news_strategy.costs import CostConfig, apply_costs
            
            # Use exit config from config file
            exit_cfg = ExitConfig(**self.config["exits"])
            trades_df = simulate_exits(trades_df, prices, exit_cfg)
            
            # Apply costs
            cost_cfg = CostConfig(
                commission_rate=float(self.config["trading"]["commission_rate"]),
                slippage_rate=float(self.config["trading"]["slippage_rate"]),
            )
            trades_df = apply_costs(trades_df, cost_cfg)
            
        print(f"  Generated {len(trades_df)} trades (after blackout filtering)")
        
        return trades_df
    
    def run_price_action_strategy(
        self,
        tickers: List[str],
        start: datetime,
        end: datetime,
        prices: Dict,
        **kwargs
    ) -> pd.DataFrame:
        """
        Run standalone price action strategy
        """
        print("\n" + "="*60)
        print("RUNNING PRICE ACTION STRATEGY")
        print("="*60)
        
        from strategies.price_action_standalone import PriceActionStrategy
        
        pa_strategy = PriceActionStrategy(
            min_confidence=0.70,
            atr_stop_multiplier=2.0,
            atr_target_multiplier=3.0,
            use_trend_filter=True
        )
        
        trades_df = pa_strategy.run(tickers, start, end, prices, **kwargs)
        
        if trades_df.empty:
            print(f"  Generated 0 price action trades")
            return trades_df
        
        # Calculate position size based on risk
        initial_balance = float(self.config["trading"]["initial_balance"])
        risk_pct = 0.01  # 1% risk per trade for price action
        
        # Add size and stop_dist columns
        sizes = []
        stop_dists = []
        
        for idx in trades_df.index:
            entry_price = float(trades_df.loc[idx, 'entry_price'])
            stop_loss = float(trades_df.loc[idx, 'stop_loss'])
            stop_dist = abs(entry_price - stop_loss)
            
            if stop_dist > 0:
                size = (initial_balance * risk_pct) / stop_dist
                
                # 🔧 FIX: Cap position size to max 10% of account
                max_position_value = initial_balance * 0.10
                max_size = max_position_value / entry_price
                original_size = size
                size = min(size, max_size)
                
                # 🔴 ULTRA-CONSERVATIVE MODE: Cap to 5% for stocks only
                # Check ticker suffix to identify asset class, not price
                ticker = trades_df.loc[idx, 'ticker']
                if not (ticker.endswith('=X') or ticker.endswith('-USD') or ticker.endswith('-USDT')):
                    # This is a stock (not forex or crypto)
                    ultra_conservative_max = (initial_balance * 0.05) / entry_price
                    if size > ultra_conservative_max:
                        print(f"  ⚠️ PA STOCK TOO LARGE! {ticker}: {size:.0f} → {ultra_conservative_max:.0f} shares")
                        size = ultra_conservative_max
                
                # DEBUG: Show when capping occurs
                if size < original_size * 0.99:
                    position_value = size * entry_price
                    print(f"  ✅ [PA CAPPED] {ticker}: {original_size:.0f} → {size:.0f} shares (${position_value:,.0f})")
            else:
                size = 100.0  # Default size if stop_dist is 0
            
            sizes.append(size)
            stop_dists.append(stop_dist)
        
        trades_df['size'] = sizes
        trades_df['stop_dist'] = stop_dists
        
        # Simulate exits
        from strategies.news_strategy.exits import ExitConfig, simulate_exits
        from strategies.news_strategy.costs import CostConfig, apply_costs
        
        exit_cfg = ExitConfig(**self.config["exits"])
        trades_df = simulate_exits(trades_df, prices, exit_cfg)
        
        # Apply costs
        cost_cfg = CostConfig(
            commission_rate=float(self.config["trading"]["commission_rate"]),
            slippage_rate=float(self.config["trading"]["slippage_rate"]),
        )
        trades_df = apply_costs(trades_df, cost_cfg)
        
        print(f"  Generated {len(trades_df)} price action trades")
        
        return trades_df
    
    def run_news_pa_confluence_strategy(
        self,
        tickers: List[str],
        start: datetime,
        end: datetime,
        prices: Dict,
        news_df: pd.DataFrame,
        **kwargs
    ) -> pd.DataFrame:
        """
        Run News + Price Action confluence strategy
        Only trades when news sentiment confirms PA pattern
        """
        print("\n" + "="*60)
        print("RUNNING NEWS + PRICE ACTION CONFLUENCE")
        print("="*60)
        
        from strategies.news_pa_confluence import NewsPriceActionConfluenceStrategy
        
        confluence_strategy = NewsPriceActionConfluenceStrategy(
            min_base_confidence=0.70,
            confluence_boost=0.20,
            news_lookback_hours=48,
            min_news_sentiment=0.55
        )
        
        trades_df = confluence_strategy.run(
            tickers, start, end, prices, news_df, **kwargs
        )
        
        if trades_df.empty:
            print(f"  Generated 0 News+PA confluence trades")
            return trades_df
        
        # Calculate position size
        initial_balance = float(self.config["trading"]["initial_balance"])
        risk_pct = 0.015  # 1.5% risk for confluence trades (higher conviction)
        
        sizes = []
        stop_dists = []
        
        for idx in trades_df.index:
            entry_price = float(trades_df.loc[idx, 'entry_price'])
            stop_loss = float(trades_df.loc[idx, 'stop_loss'])
            stop_dist = abs(entry_price - stop_loss)
            
            if stop_dist > 0:
                size = (initial_balance * risk_pct) / stop_dist
                
                # 🔧 FIX: Cap position size to max 10% of account
                max_position_value = initial_balance * 0.10
                max_size = max_position_value / entry_price
                size = min(size, max_size)
            else:
                size = 100.0
            
            sizes.append(size)
            stop_dists.append(stop_dist)
        
        trades_df['size'] = sizes
        trades_df['stop_dist'] = stop_dists
        
        # Simulate exits
        from strategies.news_strategy.exits import ExitConfig, simulate_exits
        from strategies.news_strategy.costs import CostConfig, apply_costs
        
        exit_cfg = ExitConfig(**self.config["exits"])
        trades_df = simulate_exits(trades_df, prices, exit_cfg)
        
        # Apply costs
        cost_cfg = CostConfig(
            commission_rate=float(self.config["trading"]["commission_rate"]),
            slippage_rate=float(self.config["trading"]["slippage_rate"]),
        )
        trades_df = apply_costs(trades_df, cost_cfg)
        
        print(f"  Generated {len(trades_df)} News+PA confluence trades")
        
        return trades_df
    
    def run_mr_pa_confluence_strategy(
        self,
        tickers: List[str],
        start: datetime,
        end: datetime,
        prices: Dict,
        mr_signals: pd.DataFrame,
        **kwargs
    ) -> pd.DataFrame:
        """
        Run Mean Reversion + Price Action confluence strategy
        Only trades when MR and PA both signal same direction
        """
        print("\n" + "="*60)
        print("RUNNING MR + PRICE ACTION CONFLUENCE")
        print("="*60)
        
        from strategies.mr_pa_confluence import MeanReversionPriceActionConfluenceStrategy
        
        confluence_strategy = MeanReversionPriceActionConfluenceStrategy(
            min_base_confidence=0.70,
            confluence_boost=0.20,
            time_window_days=2,
            price_tolerance_pct=0.05
        )
        
        trades_df = confluence_strategy.run(
            tickers, start, end, prices, mr_signals, **kwargs
        )
        
        if trades_df.empty:
            print(f"  Generated 0 MR+PA confluence trades")
            return trades_df
        
        # Calculate position size
        initial_balance = float(self.config["trading"]["initial_balance"])
        risk_pct = 0.015  # 1.5% risk for confluence trades (higher conviction)
        
        sizes = []
        stop_dists = []
        
        for idx in trades_df.index:
            entry_price = float(trades_df.loc[idx, 'entry_price'])
            stop_loss = float(trades_df.loc[idx, 'stop_loss'])
            stop_dist = abs(entry_price - stop_loss)
            
            if stop_dist > 0:
                size = (initial_balance * risk_pct) / stop_dist
                
                # 🔧 FIX: Cap position size to max 10% of account
                max_position_value = initial_balance * 0.10
                max_size = max_position_value / entry_price
                size = min(size, max_size)
            else:
                size = 100.0
            
            sizes.append(size)
            stop_dists.append(stop_dist)
        
        trades_df['size'] = sizes
        trades_df['stop_dist'] = stop_dists
        
        # Simulate exits
        from strategies.news_strategy.exits import ExitConfig, simulate_exits
        from strategies.news_strategy.costs import CostConfig, apply_costs
        
        exit_cfg = ExitConfig(**self.config["exits"])
        trades_df = simulate_exits(trades_df, prices, exit_cfg)
        
        # Apply costs
        cost_cfg = CostConfig(
            commission_rate=float(self.config["trading"]["commission_rate"]),
            slippage_rate=float(self.config["trading"]["slippage_rate"]),
        )
        trades_df = apply_costs(trades_df, cost_cfg)
        
        print(f"  Generated {len(trades_df)} MR+PA confluence trades")
        
        return trades_df
        
    def combine_results(self) -> pd.DataFrame:
        """
        Combine all strategy results into unified DataFrame
        """
        all_dfs = []
        
        # Normalize timezone in each DataFrame before combining
        if not self.news_trades.empty:
            df = self.news_trades.copy()
            if 'entry_time' in df.columns:
                df['entry_time'] = pd.to_datetime(df['entry_time'])
                if hasattr(df['entry_time'].dtype, 'tz') and df['entry_time'].dt.tz is not None:
                    df['entry_time'] = df['entry_time'].dt.tz_localize(None)
            all_dfs.append(df)
            
        if not self.earnings_trades.empty:
            df = self.earnings_trades.copy()
            if 'entry_time' in df.columns:
                df['entry_time'] = pd.to_datetime(df['entry_time'])
                if hasattr(df['entry_time'].dtype, 'tz') and df['entry_time'].dt.tz is not None:
                    df['entry_time'] = df['entry_time'].dt.tz_localize(None)
            all_dfs.append(df)
            
        if not self.mean_reversion_trades.empty:
            df = self.mean_reversion_trades.copy()
            if 'entry_time' in df.columns:
                df['entry_time'] = pd.to_datetime(df['entry_time'])
                if hasattr(df['entry_time'].dtype, 'tz') and df['entry_time'].dt.tz is not None:
                    df['entry_time'] = df['entry_time'].dt.tz_localize(None)
            all_dfs.append(df)
        
        # NEW: Add price action trades
        if not self.price_action_trades.empty:
            df = self.price_action_trades.copy()
            if 'entry_time' in df.columns:
                df['entry_time'] = pd.to_datetime(df['entry_time'])
                if hasattr(df['entry_time'].dtype, 'tz') and df['entry_time'].dt.tz is not None:
                    df['entry_time'] = df['entry_time'].dt.tz_localize(None)
            all_dfs.append(df)
        
        # NEW: Add news+PA confluence trades
        if not self.news_pa_confluence_trades.empty:
            df = self.news_pa_confluence_trades.copy()
            if 'entry_time' in df.columns:
                df['entry_time'] = pd.to_datetime(df['entry_time'])
                if hasattr(df['entry_time'].dtype, 'tz') and df['entry_time'].dt.tz is not None:
                    df['entry_time'] = df['entry_time'].dt.tz_localize(None)
            all_dfs.append(df)
        
        # NEW: Add MR+PA confluence trades
        if not self.mr_pa_confluence_trades.empty:
            df = self.mr_pa_confluence_trades.copy()
            if 'entry_time' in df.columns:
                df['entry_time'] = pd.to_datetime(df['entry_time'])
                if hasattr(df['entry_time'].dtype, 'tz') and df['entry_time'].dt.tz is not None:
                    df['entry_time'] = df['entry_time'].dt.tz_localize(None)
            all_dfs.append(df)
            
        if all_dfs:
            self.all_trades = pd.concat(all_dfs, ignore_index=True)
            # Sort by entry time (all are now timezone-naive)
            if 'entry_time' in self.all_trades.columns:
                self.all_trades = self.all_trades.sort_values('entry_time').reset_index(drop=True)
        else:
            self.all_trades = pd.DataFrame()
            
        return self.all_trades
        
    def generate_summary(self) -> Dict:
        """Generate summary statistics"""
        if self.all_trades.empty:
            return {
                "total_trades": 0,
                "strategies": {},
                "event_stats": self.event_coordinator.get_statistics()
            }
            
        summary = {
            "total_trades": len(self.all_trades),
            "strategies": {},
            "event_stats": self.event_coordinator.get_statistics()
        }
        
        # Per-strategy stats
        for strategy in self.all_trades['strategy'].unique():
            strategy_trades = self.all_trades[self.all_trades['strategy'] == strategy]
            
            strategy_summary = {
                "trades": len(strategy_trades),
                "tickers": strategy_trades['ticker'].nunique() if 'ticker' in strategy_trades.columns else 0,
            }
            
            # Add PnL if available (check both pnl_net and pnl columns)
            pnl_col = None
            if 'pnl_net' in strategy_trades.columns:
                pnl_col = 'pnl_net'
            elif 'pnl' in strategy_trades.columns:
                pnl_col = 'pnl'
                
            if pnl_col:
                strategy_summary['total_pnl'] = float(strategy_trades[pnl_col].sum())
                strategy_summary['avg_pnl'] = float(strategy_trades[pnl_col].mean())
            else:
                # No P&L column found - set to 0
                strategy_summary['total_pnl'] = 0.0
                strategy_summary['avg_pnl'] = 0.0
                
            summary['strategies'][strategy] = strategy_summary
            
        return summary
        
    def export_results(self, output_dir: str = "outputs"):
        """Export all results to files"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Export combined trades
        if not self.all_trades.empty:
            filename = output_path / f"unified_trades_{timestamp}.csv"
            self.all_trades.to_csv(filename, index=False)
            print(f"\n[SAVED] Unified trades: {filename}")
            
        # Export per-strategy results
        if not self.news_trades.empty:
            filename = output_path / f"news_macro_trades_{timestamp}.csv"
            self.news_trades.to_csv(filename, index=False)
            print(f"[SAVED] News/Macro trades: {filename}")
            
        if not self.earnings_trades.empty:
            filename = output_path / f"earnings_insider_trades_{timestamp}.csv"
            self.earnings_trades.to_csv(filename, index=False)
            print(f"[SAVED] Earnings/Insider trades: {filename}")
            
        if not self.mean_reversion_trades.empty:
            filename = output_path / f"mean_reversion_trades_{timestamp}.csv"
            self.mean_reversion_trades.to_csv(filename, index=False)
            print(f"[SAVED] Mean Reversion trades: {filename}")
            
        # Export summary
        summary = self.generate_summary()
        import json
        summary_file = output_path / f"summary_{timestamp}.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        print(f"[SAVED] Summary: {summary_file}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Unified Trading System - News/Macro + Earnings/Insider + Mean Reversion"
    )
    
    # Mode selection
    parser.add_argument("--mode", default="backtest", choices=["backtest", "live"],
                       help="Run mode: backtest or live trading")
    
    # Ticker configuration
    ticker_group = parser.add_mutually_exclusive_group(required=True)
    ticker_group.add_argument("--tickers", nargs='+', 
                              help="Ticker symbol(s) to trade (e.g., AAPL MSFT or EURUSD=X)")
    ticker_group.add_argument("--tickers-file", 
                              help="Path to tickers file (one ticker per line)")
    
    # Date range options - either lookback OR custom range
    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument("--lookback-days", type=int, default=90, 
                           help="Lookback period in days (default: 90)")
    date_group.add_argument("--date-range", nargs=2, metavar=("START", "END"),
                           help="Custom date range (YYYY-MM-DD YYYY-MM-DD)")
    
    # Trading parameters
    parser.add_argument("--interval", default="1d", choices=["1d", "1h", "30m", "15m", "5m", "1m"])
    parser.add_argument("--config", default="config/config.yaml", help="Path to config file")
    parser.add_argument("--outputs", default="outputs", help="Output directory")
    parser.add_argument("--price-cache", default="price_cache", help="Price cache directory")
    parser.add_argument("--cache-dir", default="cache", help="General cache directory")
    parser.add_argument("--sec-user-agent", 
                       default="Automated Trading System trading@system.com",
                       help='SEC User-Agent (e.g., "YourName your@email.com")')
    parser.add_argument("--asset-type", default="stocks", choices=["stocks", "forex", "crypto"])
    
    args = parser.parse_args()
    
    # Load environment
    load_dotenv(override=True)
    
    # Check mode
    if args.mode == "live":
        print("\n[INFO] Starting live trading mode...")
        from live_trading import run_live_trading
        run_live_trading(args)
        return
    
    # Backtest mode
    # Read tickers
    if args.tickers:
        # Direct ticker symbols provided
        tickers = [t.upper() for t in args.tickers]
        print(f"[INFO] Trading {len(tickers)} ticker(s): {', '.join(tickers)}")
    elif args.tickers_file:
        # Read from file
        tickers_path = Path(args.tickers_file)
        if not tickers_path.exists():
            print(f"[ERROR] Tickers file not found: {args.tickers_file}")
            return
        
        tickers = []
        for line in tickers_path.read_text().splitlines():
            ticker = line.strip().upper()
            if ticker and not ticker.startswith('#'):
                tickers.append(ticker)
        print(f"[INFO] Loaded {len(tickers)} ticker(s) from {args.tickers_file}")
    else:
        print("[ERROR] Must provide either --tickers or --tickers-file")
        return
            
    if not tickers:
        print("[ERROR] No tickers found")
        return
        
    print(f"\n[INFO] Loaded {len(tickers)} tickers")
    
    # Calculate date range
    if args.date_range:
        # Custom date range provided
        try:
            start = datetime.strptime(args.date_range[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            end = datetime.strptime(args.date_range[1], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            print(f"[INFO] Using custom date range: {start.date()} to {end.date()}")
        except ValueError as e:
            print(f"[ERROR] Invalid date format. Use YYYY-MM-DD: {e}")
            return
    else:
        # Use lookback days
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=args.lookback_days)
        print(f"[INFO] Using lookback: {args.lookback_days} days")
    
    print(f"[INFO] Backtest period: {start.date()} to {end.date()}")
    print(f"[INFO] Interval: {args.interval}")
    
    # Create unified backtest
    backtest = UnifiedBacktest(config_path=args.config)
    
    # Run strategies
    try:
        # 1. News/Macro Strategy
        backtest.news_trades = backtest.run_news_macro_strategy(
            tickers=tickers,
            start=start,
            end=end,
            interval=args.interval,
            price_cache=args.price_cache
        )
        
        # 2. Earnings/Insider Strategy
        backtest.earnings_trades = backtest.run_earnings_insider_strategy(
            tickers=tickers,
            start=start,
            end=end,
            sec_user_agent=args.sec_user_agent,
            cache_dir=args.cache_dir
        )
        
        # 3. Mean Reversion Strategy (with event blackout)
        backtest.mean_reversion_trades = backtest.run_mean_reversion_strategy(
            tickers=tickers,
            start=start,
            end=end,
            interval=args.interval,
            asset_type=args.asset_type
        )
        
        # Combine and export results
        backtest.combine_results()
        backtest.export_results(output_dir=args.outputs)
        
        # Print summary
        summary = backtest.generate_summary()
        print("\n" + "="*60)
        print("BACKTEST SUMMARY")
        print("="*60)
        print(f"Total Trades: {summary['total_trades']}")
        print(f"\nEvent Statistics:")
        for key, val in summary['event_stats'].items():
            print(f"  {key}: {val}")
        print(f"\nPer-Strategy Results:")
        for strategy, stats in summary['strategies'].items():
            print(f"\n  {strategy}:")
            for key, val in stats.items():
                print(f"    {key}: {val}")
                
        print("\n[DONE] Unified backtest complete!")
        
    except Exception as e:
        print(f"\n[ERROR] Backtest failed: {str(e)}")
        import traceback
        traceback.print_exc()
        

if __name__ == "__main__":
    main()
