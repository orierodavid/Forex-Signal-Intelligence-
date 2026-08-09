from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .base import Strategy, StrategyContext, StrategyResult
from .strategies import DEFAULT_STRATEGIES


@dataclass(frozen=True)
class StrategySelection:
    selected: StrategyResult | None
    candidates: tuple[StrategyResult, ...]
    threshold: float

    @property
    def direction(self) -> str:
        return self.selected.direction if self.selected else "NO_TRADE"


class StrategySelector:
    """Select one regime-compatible strategy; contradictory candidates never become a signal."""

    def __init__(self, strategies: Iterable[Strategy] = DEFAULT_STRATEGIES, minimum_score: float = 70.0) -> None:
        if not 0 <= minimum_score <= 100:
            raise ValueError("minimum_score must be between 0 and 100")
        self.strategies = tuple(strategies)
        self.minimum_score = minimum_score

    def evaluate(self, context: StrategyContext) -> StrategySelection:
        candidates = tuple(strategy.evaluate(context) for strategy in self.strategies)
        eligible = [candidate for candidate in candidates if candidate.eligible and candidate.score >= self.minimum_score]
        if not eligible:
            return StrategySelection(None, candidates, self.minimum_score)

        eligible.sort(key=lambda item: (-item.score, item.strategy))
        winner = eligible[0]

        # Require a meaningful score advantage when the top candidates disagree.
        opposing = [candidate for candidate in eligible[1:] if candidate.direction != winner.direction]
        if opposing and winner.score - opposing[0].score < 5.0:
            return StrategySelection(None, candidates, self.minimum_score)
        return StrategySelection(winner, candidates, self.minimum_score)
