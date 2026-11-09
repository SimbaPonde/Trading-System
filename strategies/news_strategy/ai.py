from __future__ import annotations
from dataclasses import dataclass
import math

@dataclass
class AIConfig:
    enabled: bool = True

class AIRanker:
    def __init__(self, cfg: AIConfig):
        self.cfg = cfg

    def score(self, *, sentiment: float, macro_alignment: float, trend: float) -> float:
        if not self.cfg.enabled:
            return 0.5
        x = 1.8 * sentiment + 1.2 * macro_alignment + 0.8 * trend
        return 1.0 / (1.0 + math.exp(-x))
