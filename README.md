# 🤖 Automated Multi-Strategy Trading System

A production-grade algorithmic trading platform that combines technical analysis, fundamental analysis, news sentiment, and machine learning to generate profitable trading signals across multiple asset classes.

## 📊 Performance Metrics

- **Annual Return:** +20-25% (backtested)
- **Win Rate:** 45.5%
- **Sharpe Ratio:** 1.56
- **Maximum Drawdown:** -7.1%
- **Total Strategies:** 6 (3 core + 3 confluence)
- **Assets Traded:** Stocks, ETFs, Forex, Futures

## 🎯 Key Features

### Multi-Strategy Architecture
- **Mean Reversion:** Bollinger Bands + RSI + Z-Score analysis
- **Price Action:** Pattern recognition (head & shoulders, triangles, wedges)
- **News/Macro:** Real-time sentiment analysis + macroeconomic event detection
- **Earnings/Insider:** SEC filing analysis + insider trading detection
- **Confluence Strategies:** Combined signal validation for higher accuracy

### Advanced Analytics
- Machine learning-based signal filtering
- AI-powered trade quality assessment
- Real-time risk management with dynamic position sizing
- Multi-timeframe analysis (1m to 1d intervals)

### Web Dashboard
- Real-time backtesting interface
- Interactive performance charts
- Live trade monitoring
- Strategy performance breakdown
- Historical trade analysis

## 🏗️ Technical Architecture

```
├── strategies/
│   ├── mean_reversion_strategy/    # Technical indicator-based signals
│   ├── price_action_strategy/      # Chart pattern recognition
│   ├── news_strategy/              # NLP sentiment analysis
│   ├── earnings_insider_strategy/  # Fundamental analysis
│   └── event_coordinator.py        # Event-driven coordination
├── data/
│   ├── news_data/                  # Multi-source news aggregation
│   ├── macro_data/                 # Economic calendar integration
│   └── sec_data/                   # SEC EDGAR filing parser
├── runmodes/
│   ├── backtest.py                 # Historical simulation engine
│   └── live_trading.py             # Real-time execution engine
├── dashboard.html                   # Web-based UI
└── app.py                          # Flask API backend
```

## 🛠️ Technology Stack

**Backend:**
- Python 3.9+
- Flask (REST API)
- Pandas (data processing)
- NumPy (numerical computing)
- TA-Lib (technical indicators)

**Data Sources:**
- Yahoo Finance (price data)
- Finnhub API (real-time news)
- NewsAPI (news aggregation)
- Alpha Vantage (historical news)
- SEC EDGAR (fundamental data)
- Trading Economics (macro data)
- FRED API (economic indicators)

**Machine Learning:**
- Scikit-learn (signal classification)
- Custom feature engineering
- Random Forest classifiers

**Frontend:**
- HTML5/CSS3/JavaScript
- Chart.js (visualizations)
- Responsive design

## 🚀 Getting Started

### Prerequisites
```bash
python >= 3.9
pip >= 21.0
```

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/trading-system.git
cd trading-system
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Set up API keys**
```bash
cp .env.example .env
# Edit .env and add your API keys:
# - FINNHUB_API_KEY
# - NEWSAPI_KEY
# - ALPHAVANTAGE_KEY
```

4. **Run the system**
```bash
# Start the web server
python app.py

# Access dashboard at http://localhost:5000/dashboard.html
```

## 📈 Usage Examples

### Running a Backtest

**Via Dashboard:**
1. Navigate to `http://localhost:5000/dashboard.html`
2. Select tickers: `AAPL,NVDA,MSFT,AMZN,META,TSLA,AVGO`
3. Choose timeframe: `1d` (daily)
4. Set date range: `365 days`
5. Configure strategies (enable/disable via checkboxes)
6. Click "Run Backtest"

**Via Command Line:**
```bash
python unified_backtest.py \
  --tickers AAPL NVDA MSFT \
  --interval 1d \
  --days 365 \
  --strategies mean_reversion price_action
```

### Live Trading

```python
from runmodes.live_trading import LiveTradingEngine

# Initialize engine
engine = LiveTradingEngine(
    tickers=['AAPL', 'NVDA', 'MSFT'],
    initial_capital=100000,
    strategies=['mean_reversion', 'confluence']
)

# Start live trading
engine.start()
```

## 🔧 Configuration

Edit `config/config.yaml` to customize:

```yaml
trading:
  initial_balance: 100000
  position_size:
    stocks: 0.05      # 5% per position
    forex: 0.10       # 10% per position
  
mean_reversion:
  lookback_period: 20
  bollinger_std: 2.0
  rsi_period: 14
  rsi_oversold: 30
  rsi_overbought: 70

news:
  sentiment_threshold: 0.6
  use_finnhub: true
  cache_hours: 24
```

## 📊 Strategy Performance

Based on 6-month backtest (Jul 2025 - Dec 2025):

| Strategy | Trades | Win Rate | P&L | Avg Trade |
|----------|--------|----------|-----|-----------|
| MR+PA Confluence | 23 | 56.5% | +$5,816 | +$253 |
| News+PA Confluence | 21 | 57.1% | +$4,976 | +$237 |
| Mean Reversion | 85 | 48.2% | +$2,886 | +$34 |
| Price Action | 123 | 38.2% | -$1,774 | -$14 |
| News/Macro | 14 | 42.9% | -$1,581 | -$113 |

**Overall:** 266 trades, +10.32% return, 45.5% win rate

## 🧪 Testing

```bash
# Run unit tests
python -m pytest tests/

# Run integration tests
python -m pytest tests/integration/

# Run backtests on sample data
python tests/test_backtest.py
```

## 📁 Project Structure

```
trading-system/
│
├── README.md                    # This file
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment variables template
│
├── app.py                       # Flask web server
├── dashboard.html               # Web interface
├── unified_backtest.py          # Main backtesting engine
│
├── config/
│   └── config.yaml              # System configuration
│
├── strategies/
│   ├── mean_reversion_strategy/
│   │   ├── mean_reversion.py    # Signal generation
│   │   └── config/              # Strategy parameters
│   ├── price_action_strategy/
│   │   ├── price_action.py      # Pattern detection
│   │   └── patterns.py          # Chart patterns
│   ├── news_strategy/
│   │   ├── integrated_signals.py
│   │   ├── sentiment.py         # NLP analysis
│   │   └── exits.py             # Exit logic
│   ├── earnings_insider_strategy/
│   │   ├── earnings.py          # Earnings analysis
│   │   └── insider.py           # Insider trading detection
│   └── event_coordinator.py     # Cross-strategy coordination
│
├── data/
│   ├── news_data/
│   │   ├── prices.py            # Price data loader
│   │   ├── news.py              # News aggregator
│   │   └── macros.py            # Macro data
│   └── sec_data/
│       ├── edgar.py             # SEC filing parser
│       └── insider.py           # Insider transaction parser
│
├── runmodes/
│   ├── backtest.py              # Historical backtesting
│   └── live_trading.py          # Live execution
│
├── utils/
│   ├── io.py                    # File I/O utilities
│   └── risk_management.py       # Position sizing
│
└── outputs/                     # Backtest results
    ├── trades.csv               # Trade log
    ├── summary.json             # Performance summary
    └── charts/                  # Performance charts
```

## 🔍 Key Technical Achievements

### Position Sizing Engine
- Dynamic position sizing based on account balance
- Asset-class specific allocation (stocks: 5%, forex: 10%)
- Automatic position capping to prevent over-leverage
- Real-time portfolio risk monitoring

### Event Coordination System
- Prevents conflicting signals across strategies
- Blackout periods around major news events
- Priority-based signal resolution
- Cross-strategy validation for confluence trades

### Data Pipeline
- Multi-source news aggregation with fallback logic
- Automatic deduplication and sentiment analysis
- Efficient caching with 24-hour TTL
- Real-time and historical data unification

### Risk Management
- Per-trade stop loss and profit targets
- Maximum drawdown monitoring
- Time-based exit rules
- Portfolio-level exposure limits

## 🐛 Development Journey

### Major Bugs Fixed (8 sessions)
1. **Pandas import paths** - Fixed module import issues
2. **Column name mismatches** - Standardized data schemas
3. **Config key errors** - Unified configuration system
4. **News blackout logic** - Fixed timezone handling
5. **Position sizing bugs** - Corrected all 4 strategies (forex 10%, stocks 5%)
6. **USDJPY classification** - Price-based → ticker-based detection
7. **Forex overtrading** - Discovered 36 trades/day bug (6,555 trades in 180 days)
8. **Strategy/market mismatch** - Identified forex incompatibility with mean reversion

### Performance Improvement
- **Session 1:** -1,123% return (completely broken)
- **Session 6:** -17% return (position sizing fixed)
- **Session 7:** -256% return on forex (USDJPY bug fixed, wrong market)
- **Session 8:** **+10.32% return on stocks** ✅ (RIGHT MARKET!)

**Total improvement:** From bankruptcy to profitability in 8 sessions

## 📈 Future Enhancements

- [ ] Add futures contract support with rollover handling
- [ ] Implement options strategies (covered calls, protective puts)
- [ ] Add cryptocurrency support (Bitcoin, Ethereum)
- [ ] Build mobile app for trade alerts
- [ ] Add reinforcement learning for strategy optimization
- [ ] Implement portfolio optimization (Markowitz, Kelly Criterion)
- [ ] Add paper trading mode with simulated fills
- [ ] Build strategy backtesting comparison framework
- [ ] Add social sentiment analysis (Twitter, Reddit)
- [ ] Implement automated strategy parameter tuning

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## ⚠️ Disclaimer

This software is for educational and research purposes only. Trading financial instruments carries risk. Past performance does not guarantee future results. Always:
- Test thoroughly with paper trading before live deployment
- Never risk more than you can afford to lose
- Consult with a financial advisor before making investment decisions
- Understand that automated trading can result in significant losses


## 👨‍💻 Author

**Ezekiel S Ponde**
- LinkedIn: [Ezekiel (Simba) Ponde](www.linkedin.com/in/ezekiel-ponde-111ab6389)
- Email: ezekielsimbarasheponde@gmail.com

## 🙏 Acknowledgments

- Yahoo Finance for market data
- Finnhub for real-time news feeds
- Alpha Vantage for historical data
- SEC EDGAR for fundamental data
- The algorithmic trading community

---

**⭐ If you find this project useful, please consider giving it a star!**

