from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class StrategyProfile:
    """Validated pair/regime strategy assignments produced by walk-forward research."""

    assignments: Mapping[str, str]
    min_trades: int = 30
    min_expectancy_r: float = 0.0
    min_profit_factor: float = 1.05

    def strategy_for(self, pair: str, regime: str) -> str | None:
        return self.assignments.get(f"{pair.upper()}|{regime.upper()}")


def load_strategy_profile(path: str | None = None) -> StrategyProfile | None:
    filename = path or os.getenv("STRATEGY_PROFILE_PATH", "strategy_profile.json")
    file = Path(filename)
    if not file.exists():
        return None
    data = json.loads(file.read_text(encoding="utf-8"))
    assignments = data.get("assignments", {})
    if not isinstance(assignments, dict):
        raise ValueError("strategy profile assignments must be an object")
    return StrategyProfile(
        assignments={str(k).upper(): str(v) for k, v in assignments.items()},
        min_trades=int(data.get("min_trades", 30)),
        min_expectancy_r=float(data.get("min_expectancy_r", 0.0)),
        min_profit_factor=float(data.get("min_profit_factor", 1.05)),
    )
