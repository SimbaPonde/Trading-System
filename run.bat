@echo off
REM Unified Trading System - Windows Batch Script

echo ==========================================
echo Unified Trading System
echo ==========================================
echo.

REM Check if SEC user agent is provided
if "%~1"=="" (
    echo Usage: run.bat "YourName your@email.com" [mode] [options]
    echo.
    echo Modes:
    echo   backtest - Run historical backtest ^(default^)
    echo   live     - Run live trading ^(paper trading^)
    echo.
    echo Examples:
    echo   run.bat "John Smith john@example.com"
    echo   run.bat "John Smith john@example.com" backtest
    echo   run.bat "John Smith john@example.com" live
    echo.
    exit /b 1
)

REM Parse arguments
set SEC_USER_AGENT=%~1
set MODE=%~2
if "%MODE%"=="" set MODE=backtest

REM Default parameters
set TICKERS=tickers.txt
set LOOKBACK=90
set INTERVAL=1d
set CONFIG=config/config.yaml
set OUTPUTS=outputs
set ASSET_TYPE=stocks

echo Configuration:
echo   Mode: %MODE%
echo   Tickers: %TICKERS%
echo   SEC User-Agent: %SEC_USER_AGENT%
echo.

if "%MODE%"=="live" (
    echo Starting LIVE TRADING mode...
    echo [WARNING] This is paper trading by default
    echo.
    python unified_backtest.py --mode live --tickers %TICKERS% --interval %INTERVAL% --config %CONFIG% --outputs %OUTPUTS% --sec-user-agent "%SEC_USER_AGENT%" --asset-type %ASSET_TYPE%
) else (
    echo Starting BACKTEST mode...
    echo   Lookback: %LOOKBACK% days
    echo   Interval: %INTERVAL%
    echo   Asset Type: %ASSET_TYPE%
    echo.
    python unified_backtest.py --mode backtest --tickers %TICKERS% --lookback-days %LOOKBACK% --interval %INTERVAL% --config %CONFIG% --outputs %OUTPUTS% --sec-user-agent "%SEC_USER_AGENT%" --asset-type %ASSET_TYPE%
)

echo.
echo ==========================================
if "%MODE%"=="live" (
    echo Live trading stopped
) else (
    echo Backtest Complete!
    echo Check the outputs/ directory for results
)
echo ==========================================
pause
