from __future__ import annotations
from dataclasses import dataclass
import pandas as pd

@dataclass
class CostConfig:
    commission_rate: float = 0.001
    slippage_rate: float = 0.0005

def apply_costs(trades: pd.DataFrame, cfg: CostConfig) -> pd.DataFrame:
    if trades.empty:
        return trades
    
    trades = trades.copy()
    
    # Calculate costs for each trade
    for idx, tr in trades.iterrows():
        entry_price = float(tr["entry_price"])
        exit_price = float(tr.get("exit_price", entry_price))
        size = int(tr["size"])
        side = tr["side"]
        
        # Calculate slippage (applied to both entry and exit)
        entry_slippage_pct = cfg.slippage_rate
        exit_slippage_pct = cfg.slippage_rate
        
        # Adjusted prices (worse fill due to slippage)
        if side == "BUY":
            entry_price_adj = entry_price * (1 + entry_slippage_pct)
            exit_price_adj = exit_price * (1 - exit_slippage_pct)
        else:  # SELL
            entry_price_adj = entry_price * (1 - entry_slippage_pct)
            exit_price_adj = exit_price * (1 + exit_slippage_pct)
        
        # Calculate costs
        entry_value = entry_price * size
        exit_value = exit_price * size
        
        # Slippage cost (difference between ideal and actual prices)
        entry_slippage_cost = abs(entry_price_adj - entry_price) * size
        exit_slippage_cost = abs(exit_price_adj - exit_price) * size
        slippage_cost = entry_slippage_cost + exit_slippage_cost
        
        # Commission (percentage of trade value, both entry and exit)
        entry_commission = entry_value * cfg.commission_rate
        exit_commission = exit_value * cfg.commission_rate
        commission_cost = entry_commission + exit_commission
        
        # Total transaction cost
        transaction_cost = slippage_cost + commission_cost
        
        # PnL calculations
        if side == "BUY":
            pnl_gross = (exit_price_adj - entry_price_adj) * size
        else:  # SELL
            pnl_gross = (entry_price_adj - exit_price_adj) * size
        
        pnl_net = pnl_gross - transaction_cost
        
        # Update trade with all cost details
        trades.at[idx, "entry_price_adj"] = float(entry_price_adj)
        trades.at[idx, "exit_price_adj"] = float(exit_price_adj)
        trades.at[idx, "slippage_cost"] = float(slippage_cost)
        trades.at[idx, "commission_cost"] = float(commission_cost)
        trades.at[idx, "transaction_cost"] = float(transaction_cost)
        trades.at[idx, "pnl_gross"] = float(pnl_gross)
        trades.at[idx, "pnl_net"] = float(pnl_net)
    
    return trades
