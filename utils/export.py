from __future__ import annotations
import os
import json
import pandas as pd
from typing import Dict

def export_outputs(out_dir: str, *, trades: pd.DataFrame, news: pd.DataFrame, macros: pd.DataFrame, summary: Dict) -> None:
    os.makedirs(out_dir, exist_ok=True)

    trades.to_csv(os.path.join(out_dir, "all_trades.csv"), index=False)

    if not trades.empty and "category" in trades.columns:
        trades[trades["category"] == "News"].to_csv(os.path.join(out_dir, "news_only.csv"), index=False)
        trades[trades["category"] == "Macro"].to_csv(os.path.join(out_dir, "macro_only.csv"), index=False)
        trades[trades["category"] == "Confluence"].to_csv(os.path.join(out_dir, "confluence.csv"), index=False)
    else:
        pd.DataFrame().to_csv(os.path.join(out_dir, "news_only.csv"), index=False)
        pd.DataFrame().to_csv(os.path.join(out_dir, "macro_only.csv"), index=False)
        pd.DataFrame().to_csv(os.path.join(out_dir, "confluence.csv"), index=False)

    news.to_csv(os.path.join(out_dir, "news.csv"), index=False)
    macros.to_csv(os.path.join(out_dir, "macros.csv"), index=False)

    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
