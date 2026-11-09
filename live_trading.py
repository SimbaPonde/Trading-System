"""
Live Trading Module
Real-time trading with all three strategies
"""
from __future__ import annotations
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List
import pandas as pd
import yaml
from dotenv import load_dotenv

from strategies.event_coordinator import EventCoordinator


class LiveTradingEngine:
    """
    Live trading engine that runs all three strategies in real-time
    """
    
    def __init__(self, config_path: str = "config/config.yaml"):
        """Initialize with configuration"""
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
            
        self.event_coordinator = EventCoordinator(
            blackout_hours=self.config['mean_reversion']['event_blackout_hours']
        )
        
        # Portfolio state
        self.portfolio: Dict = {
            'cash': float(self.config['trading']['initial_balance']),
            'positions': {},
            'pending_orders': [],
        }
        
        # Track active trades
        self.active_trades: List[Dict] = []
        
        print(f"[LIVE] Initialized with ${self.portfolio['cash']:,.2f}")
        
    def update_events(self, tickers: List[str]):
        """
        Fetch and register latest events for event coordination
        """
        print("[LIVE] Updating event data...")
        
        now = datetime.now(timezone.utc)
        lookback = now - timedelta(hours=24)  # Look back 24 hours
        lookahead = now + timedelta(hours=48)  # Look ahead 48 hours
        
        try:
            # Import data fetchers
            from data.news_data.news import NewsConfig, fetch_news
            from data.news_data.macros import MacroConfig, fetch_macros
            from data.earnings_data.earnings_source import get_earnings_events
            
            # Fetch recent and upcoming events
            news_cfg = NewsConfig(use_finnhub=self.config["news"]["use_finnhub"])
            news = fetch_news(tickers, start=lookback, end=lookahead, cfg=news_cfg)
            
            macro_cfg = MacroConfig(
                include_event_types=self.config["macros"]["include_event_types"],
                redundant_sources=self.config["macros"]["redundant_sources"],
            )
            macros = fetch_macros(start=lookback, end=lookahead, cfg=macro_cfg)
            
            # Fetch earnings (next 7 days)
            earnings_frames = []
            for ticker in tickers:
                try:
                    df = get_earnings_events(ticker, lookback.date(), lookahead.date())
                    if df is not None and not df.empty:
                        earnings_frames.append(df)
                except Exception as e:
                    print(f"  [WARNING] Could not fetch earnings for {ticker}: {e}")
                    
            earnings = pd.concat(earnings_frames, ignore_index=True) if earnings_frames else pd.DataFrame()
            
            # Register events with coordinator
            self.event_coordinator.register_events(
                news_df=news,
                macro_df=macros,
                earnings_df=earnings
            )
            
            stats = self.event_coordinator.get_statistics()
            print(f"  Events registered: {stats['news_events']} news, {stats['macro_events']} macro, {stats['earnings_events']} earnings")
            
        except Exception as e:
            print(f"  [ERROR] Failed to update events: {e}")
            
    def scan_for_signals(self, tickers: List[str], interval: str = "1d") -> List[Dict]:
        """
        Scan for trading signals from all strategies
        """
        signals = []
        now = datetime.now(timezone.utc)
        
        print(f"\n[LIVE] Scanning for signals at {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        
        # 1. News/Macro signals
        try:
            signals.extend(self._scan_news_macro(tickers, interval))
        except Exception as e:
            print(f"  [ERROR] News/Macro scan failed: {e}")
            
        # 2. Earnings/Insider signals
        try:
            signals.extend(self._scan_earnings_insider(tickers))
        except Exception as e:
            print(f"  [ERROR] Earnings/Insider scan failed: {e}")
            
        # 3. Mean Reversion signals (with event blackout)
        try:
            signals.extend(self._scan_mean_reversion(tickers, interval))
        except Exception as e:
            print(f"  [ERROR] Mean Reversion scan failed: {e}")
            
        print(f"  Found {len(signals)} total signals")
        return signals
        
    def _scan_news_macro(self, tickers: List[str], interval: str) -> List[Dict]:
        """Scan for news/macro signals"""
        # This would integrate with your news/macro strategy
        # For now, return empty list as placeholder
        return []
        
    def _scan_earnings_insider(self, tickers: List[str]) -> List[Dict]:
        """Scan for earnings/insider signals"""
        # This would integrate with your earnings/insider strategy
        # For now, return empty list as placeholder
        return []
        
    def _scan_mean_reversion(self, tickers: List[str], interval: str) -> List[Dict]:
        """Scan for mean reversion signals with event blackout"""
        signals = []
        now = pd.Timestamp.now(tz='UTC')
        
        # Check each ticker
        for ticker in tickers:
            # Skip if in blackout period
            if self.event_coordinator.is_blackout_period(now, ticker):
                reason = self.event_coordinator.get_blackout_reason(now, ticker)
                print(f"  [BLACKOUT] {ticker}: {reason}")
                continue
                
            # Scan for mean reversion setup
            # This would integrate with your mean reversion strategy
            # For now, placeholder
            
        return signals
        
    def execute_signal(self, signal: Dict) -> bool:
        """
        Execute a trading signal
        """
        ticker = signal.get('ticker')
        side = signal.get('side', 'BUY')
        size = signal.get('size', 0)
        price = signal.get('entry_price', 0)
        
        print(f"\n[EXECUTE] {side} {size} shares of {ticker} @ ${price:.2f}")
        
        # Check available cash
        cost = size * price
        if side == 'BUY' and cost > self.portfolio['cash']:
            print(f"  [REJECTED] Insufficient cash (need ${cost:.2f}, have ${self.portfolio['cash']:.2f})")
            return False
            
        # Execute trade (placeholder - would integrate with broker API)
        print(f"  [TODO] Would send order to broker API here")
        
        # Update portfolio (for paper trading)
        if side == 'BUY':
            self.portfolio['cash'] -= cost
            if ticker not in self.portfolio['positions']:
                self.portfolio['positions'][ticker] = {'shares': 0, 'avg_price': 0}
            pos = self.portfolio['positions'][ticker]
            total_shares = pos['shares'] + size
            pos['avg_price'] = ((pos['shares'] * pos['avg_price']) + (size * price)) / total_shares
            pos['shares'] = total_shares
        else:  # SELL
            if ticker in self.portfolio['positions']:
                pos = self.portfolio['positions'][ticker]
                if pos['shares'] >= size:
                    self.portfolio['cash'] += size * price
                    pos['shares'] -= size
                    if pos['shares'] == 0:
                        del self.portfolio['positions'][ticker]
                        
        # Track trade
        self.active_trades.append({
            'timestamp': datetime.now(timezone.utc),
            'ticker': ticker,
            'side': side,
            'size': size,
            'price': price,
            'strategy': signal.get('strategy', 'unknown'),
        })
        
        print(f"  [SUCCESS] Trade executed")
        print(f"  Cash remaining: ${self.portfolio['cash']:,.2f}")
        
        return True
        
    def check_exits(self):
        """
        Check if any positions should be exited
        """
        # This would monitor stops, targets, time-based exits, etc.
        # Placeholder for now
        pass
        
    def display_status(self):
        """Display current portfolio status"""
        print("\n" + "="*60)
        print("PORTFOLIO STATUS")
        print("="*60)
        print(f"Cash: ${self.portfolio['cash']:,.2f}")
        print(f"\nPositions: {len(self.portfolio['positions'])}")
        
        total_value = self.portfolio['cash']
        for ticker, pos in self.portfolio['positions'].items():
            value = pos['shares'] * pos['avg_price']
            total_value += value
            print(f"  {ticker}: {pos['shares']} shares @ ${pos['avg_price']:.2f} = ${value:,.2f}")
            
        print(f"\nTotal Portfolio Value: ${total_value:,.2f}")
        print(f"Total Trades: {len(self.active_trades)}")
        print("="*60 + "\n")
        
    def save_trades(self, output_dir: str = "outputs"):
        """Save trade history"""
        if not self.active_trades:
            print("[INFO] No trades to save")
            return
            
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = output_path / f"live_trades_{timestamp}.csv"
        
        df = pd.DataFrame(self.active_trades)
        df.to_csv(filename, index=False)
        print(f"[SAVED] Trade history: {filename}")


def run_live_trading(args):
    """
    Main live trading loop
    """
    print("\n" + "="*60)
    print("LIVE TRADING MODE - UNIFIED SYSTEM")
    print("="*60)
    print("\n[WARNING] This is paper trading mode by default")
    print("[WARNING] To trade with real money, integrate broker API")
    print()
    
    # Read tickers
    tickers_path = Path(args.tickers)
    if not tickers_path.exists():
        print(f"[ERROR] Tickers file not found: {args.tickers}")
        return
        
    tickers = []
    for line in tickers_path.read_text().splitlines():
        ticker = line.strip().upper()
        if ticker and not ticker.startswith('#'):
            tickers.append(ticker)
            
    if not tickers:
        print("[ERROR] No tickers found")
        return
        
    print(f"[INFO] Monitoring {len(tickers)} tickers: {', '.join(tickers[:5])}{'...' if len(tickers) > 5 else ''}")
    
    # Initialize engine
    engine = LiveTradingEngine(config_path=args.config)
    
    # Scan interval in seconds
    scan_interval = 60  # Scan every minute
    if args.interval == "1d":
        scan_interval = 3600  # Hourly for daily charts
    elif args.interval == "1h":
        scan_interval = 300  # Every 5 minutes for hourly charts
    elif args.interval in ["30m", "15m"]:
        scan_interval = 60  # Every minute for intraday
        
    print(f"[INFO] Scan interval: {scan_interval} seconds")
    print(f"[INFO] Press Ctrl+C to stop\n")
    
    try:
        iteration = 0
        while True:
            iteration += 1
            
            print(f"\n{'='*60}")
            print(f"Scan #{iteration} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*60}")
            
            # Update events every 10 iterations (~10 minutes for 1-minute scans)
            if iteration % 10 == 1:
                engine.update_events(tickers)
                
            # Scan for signals
            signals = engine.scan_for_signals(tickers, args.interval)
            
            # Execute signals
            for signal in signals:
                engine.execute_signal(signal)
                
            # Check for exits
            engine.check_exits()
            
            # Display status every 5 iterations
            if iteration % 5 == 0:
                engine.display_status()
                
            # Wait for next scan
            print(f"\n[WAIT] Next scan in {scan_interval} seconds...")
            time.sleep(scan_interval)
            
    except KeyboardInterrupt:
        print("\n\n[INFO] Stopping live trading...")
        engine.display_status()
        engine.save_trades(args.outputs)
        print("\n[DONE] Live trading stopped")


if __name__ == "__main__":
    print("This module should be run through unified_backtest.py with --mode live")
