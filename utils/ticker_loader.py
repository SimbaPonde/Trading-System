"""
Ticker Loader Utility
Loads tickers from files and validates them
"""
import os
from typing import List, Dict, Set
import pandas as pd


def load_tickers_from_file(filepath: str, skip_header: bool = True) -> List[str]:
    """
    Load tickers from a text file
    
    Args:
        filepath: Path to the ticker file
        skip_header: Whether to skip the first line (default True)
    
    Returns:
        List of ticker symbols
    """
    tickers = []
    
    if not os.path.exists(filepath):
        print(f"[WARNING] Ticker file not found: {filepath}")
        return tickers
    
    with open(filepath, 'r') as f:
        lines = f.readlines()
    
    # Skip header if requested
    if skip_header and lines:
        lines = lines[1:]
    
    for line in lines:
        ticker = line.strip()
        if ticker and not ticker.startswith('#'):  # Skip empty lines and comments
            # Remove any quotes that might have been added
            ticker = ticker.strip("'\"")
            tickers.append(ticker)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_tickers = []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            unique_tickers.append(t)
    
    print(f"[INFO] Loaded {len(unique_tickers)} tickers from {filepath}")
    return unique_tickers


def create_default_ticker_files():
    """Create default ticker list files"""
    
    # Tech stocks (optimized - only winners)
    tech_stocks = """Ticker
AMZN
META
NVDA
MSFT
"""
    
    # NAS100 stocks (full list for evaluation)
    nas100_stocks = """Ticker
AAPL
NVDA
MSFT
AMZN
META
AVGO
TSLA
COST
NFLX
TMUS
CSCO
PEP
AMD
ADBE
LIN
ISRG
BKNG
QCOM
TXN
CMCSA
HON
AMGN
AMAT
PANW
ADP
VRTX
GILD
SBUX
MU
ADI
LRCX
MELI
MRVL
PYPL
INTC
KLAC
CTAS
CRWD
CDNS
MDLZ
MAR
REGN
SNPS
FTNT
CEG
ORLY
PDD
DASH
ASML
ADSK
"""
    
    # Commodity ETFs (optimized + test candidates)
    commodity_etfs = """Ticker
SLV
CPER
PALL
GLD
PPLT
USO
UNG
DBA
DBC
"""
    
    # Index ETFs (optimized + test candidates)
    index_etfs = """Ticker
IWM
MDY
SPY
QQQ
DIA
VTI
VOO
"""
    
    # Major forex pairs
    forex_pairs = """Ticker
EURUSD=X
GBPUSD=X
USDJPY=X
AUDUSD=X
USDCAD=X
USDCHF=X
NZDUSD=X
"""
    
    # Crypto pairs
    crypto_pairs = """Ticker
BTC-USD
ETH-USD
BNB-USD
SOL-USD
"""
    
    # Create ticker_lists directory
    os.makedirs('ticker_lists', exist_ok=True)
    
    files = {
        'ticker_lists/tech_stocks_optimized.txt': tech_stocks,
        'ticker_lists/nas100_full.txt': nas100_stocks,
        'ticker_lists/commodity_etfs.txt': commodity_etfs,
        'ticker_lists/index_etfs.txt': index_etfs,
        'ticker_lists/forex_pairs.txt': forex_pairs,
        'ticker_lists/crypto_pairs.txt': crypto_pairs,
    }
    
    for filepath, content in files.items():
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"[INFO] Created {filepath}")


def load_ticker_universe(
    include_tech: bool = True,
    include_commodities: bool = False,
    include_indices: bool = False,
    include_forex: bool = False,
    include_crypto: bool = False,
    optimized_only: bool = True
) -> Dict[str, List[str]]:
    """
    Load ticker universe based on asset class preferences
    
    Args:
        include_tech: Include tech stocks
        include_commodities: Include commodity ETFs
        include_indices: Include index ETFs
        include_forex: Include forex pairs
        include_crypto: Include crypto pairs
        optimized_only: Use only optimized tickers (winners) vs full lists
    
    Returns:
        Dictionary mapping asset class to list of tickers
    """
    tickers = {}
    
    if include_tech:
        if optimized_only:
            tickers['tech'] = ['AMZN', 'META', 'NVDA']
        else:
            # Check if file exists, otherwise use default
            if os.path.exists('ticker_lists/nas100_full.txt'):
                tickers['tech'] = load_tickers_from_file('ticker_lists/nas100_full.txt')
            else:
                tickers['tech'] = ['AAPL', 'MSFT', 'AMZN', 'META', 'NVDA', 'GOOGL', 
                                  'TSLA', 'AVGO', 'COST', 'NFLX']
    
    if include_commodities:
        if optimized_only:
            tickers['commodities'] = ['SLV', 'CPER', 'PALL']
        else:
            tickers['commodities'] = ['GLD', 'SLV', 'PPLT', 'PALL', 'CPER', 
                                      'USO', 'UNG', 'DBA', 'DBC']
    
    if include_indices:
        if optimized_only:
            tickers['indices'] = ['IWM', 'MDY']
        else:
            tickers['indices'] = ['SPY', 'QQQ', 'DIA', 'IWM', 'MDY', 'VTI', 'VOO']
    
    if include_forex:
        tickers['forex'] = ['EURUSD=X', 'GBPUSD=X', 'USDJPY=X', 'AUDUSD=X']
    
    if include_crypto:
        tickers['crypto'] = ['BTC-USD', 'ETH-USD', 'BNB-USD', 'SOL-USD']
    
    return tickers


def combine_ticker_lists(ticker_dict: Dict[str, List[str]]) -> List[str]:
    """Combine multiple ticker lists into one"""
    all_tickers = []
    for asset_class, tickers in ticker_dict.items():
        all_tickers.extend(tickers)
    return all_tickers


if __name__ == '__main__':
    # Test
    print("Creating default ticker files...")
    create_default_ticker_files()
    
    print("\nLoading optimized universe...")
    universe = load_ticker_universe(
        include_tech=True,
        include_commodities=True,
        include_indices=True,
        optimized_only=True
    )
    
    for asset_class, tickers in universe.items():
        print(f"{asset_class}: {tickers}")
