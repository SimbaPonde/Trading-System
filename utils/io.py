from __future__ import annotations
import pathlib
from typing import List

def read_tickers_file(path: str) -> List[str]:
    p = pathlib.Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Tickers file not found: {path}")
    tickers = []
    for line in p.read_text(encoding="utf-8").splitlines():
        t = line.strip().upper()
        if not t or t.startswith("#"):
            continue
        tickers.append(t)
    return sorted(set(tickers))
