#!/bin/bash

# Unified Trading System - Quick Run Script
# This script runs the unified trading system with default parameters

echo "=========================================="
echo "Unified Trading System"
echo "=========================================="
echo ""

# Check if SEC user agent is provided
if [ -z "$1" ]; then
    echo "Usage: ./run.sh \"YourName your@email.com\" [mode]"
    echo ""
    echo "Modes:"
    echo "  backtest - Run historical backtest (default)"
    echo "  live     - Run live trading (paper trading)"
    echo ""
    echo "Examples:"
    echo "  ./run.sh \"John Smith john@example.com\""
    echo "  ./run.sh \"John Smith john@example.com\" backtest"
    echo "  ./run.sh \"John Smith john@example.com\" live"
    echo ""
    exit 1
fi

SEC_USER_AGENT="$1"
MODE="${2:-backtest}"

# Default parameters
TICKERS="tickers.txt"
LOOKBACK=90
INTERVAL="1d"
CONFIG="config/config.yaml"
OUTPUTS="outputs"
ASSET_TYPE="stocks"

echo "Configuration:"
echo "  Mode: $MODE"
echo "  Tickers: $TICKERS"
echo "  SEC User-Agent: $SEC_USER_AGENT"
echo ""

if [ "$MODE" = "live" ]; then
    echo "Starting LIVE TRADING mode..."
    echo "[WARNING] This is paper trading by default"
    echo ""
    python unified_backtest.py \
        --mode live \
        --tickers "$TICKERS" \
        --interval "$INTERVAL" \
        --config "$CONFIG" \
        --outputs "$OUTPUTS" \
        --sec-user-agent "$SEC_USER_AGENT" \
        --asset-type "$ASSET_TYPE"
else
    echo "Starting BACKTEST mode..."
    echo "  Lookback: $LOOKBACK days"
    echo "  Interval: $INTERVAL"
    echo "  Asset Type: $ASSET_TYPE"
    echo ""
    python unified_backtest.py \
        --mode backtest \
        --tickers "$TICKERS" \
        --lookback-days $LOOKBACK \
        --interval "$INTERVAL" \
        --config "$CONFIG" \
        --outputs "$OUTPUTS" \
        --sec-user-agent "$SEC_USER_AGENT" \
        --asset-type "$ASSET_TYPE"
fi

echo ""
echo "=========================================="
if [ "$MODE" = "live" ]; then
    echo "Live trading stopped"
else
    echo "Backtest Complete!"
    echo "Check the outputs/ directory for results"
fi
echo "=========================================="
