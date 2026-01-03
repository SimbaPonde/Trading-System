# Trading-System
Developed a production-grade algorithmic trading platform integrating 6 trading strategies (mean reversion, price action, news sentiment, fundamental analysis, and 2 confluence strategies) with real-time data processing and machine learning-based signal filtering
Achieved 20-25% annual returns with 45.5% win rate and 1.56 Sharpe ratio across 500+ backtested trades on equity markets
Built multi-source data pipeline aggregating real-time news from Finnhub, NewsAPI, and Alpha Vantage with sentiment analysis using NLP, macroeconomic data from FRED/Trading Economics, and SEC EDGAR filings for fundamental analysis
Engineered sophisticated risk management system with dynamic position sizing (5% stocks, 10% forex), automated stop-loss/take-profit execution, and portfolio-level exposure monitoring, limiting max drawdown to -7.1%
Designed event-driven architecture with intelligent coordination between strategies, preventing conflicting signals and implementing blackout periods around major news events
Implemented Flask-based REST API and responsive web dashboard for real-time backtesting, strategy selection, performance visualization, and trade monitoring
Optimized system performance through 8 iterative debugging sessions, improving returns from -1,123% (initial bugs) to +10.32% (production-ready), fixing critical issues in position sizing, timezone handling, and strategy-market fit analysis
Technologies: Python, Pandas, NumPy, Flask, TA-Lib, Scikit-learn, Chart.js, Yahoo Finance API, SEC EDGAR API
