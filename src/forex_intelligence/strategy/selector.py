from __future__ import annotations

from dataclasses import dataclass, replace
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
    """Select the single best regime/timeframe-compatible strategy.

    Quality is gated on the strategy's own score. Higher-timeframe alignment
    can rank an already-qualified candidate more strongly, but it can never
    manufacture eligibility for a candidate scoring below 80.
    """

    def __init__(self, strategies: Iterable[Strategy] = DEFAULT_STRATEGIES, minimum_score: float = 80.0) -> None:
        if not 0 <= minimum_score <= 100:
            raise ValueError("minimum_score must be between 0 and 100")
        self.strategies = tuple(strategies)
        self.minimum_score = minimum_score

    @staticmethod
    def _alignment_bonus(candidate: StrategyResult, context: StrategyContext) -> float:
        if candidate.direction not in {"BUY", "SELL"}:
            return 0.0
        bonus = 0.0
        h4 = context.regimes.get("H4", "")
        h1 = context.regimes.get("H1", context.regime)
        bullish = {"STRONG_TREND_UP", "TREND_UP"}
        bearish = {"STRONG_TREND_DOWN", "TREND_DOWN"}
        aligned = bullish if candidate.direction == "BUY" else bearish
        if h4 in aligned:
            bonus += 3.0
        if h1 in aligned:
            bonus += 2.0
        return bonus

    def evaluate(self, context: StrategyContext) -> StrategySelection:
        raw_candidates = tuple(strategy.evaluate(context) for strategy in self.strategies)
        # Preserve the raw score as the eligibility gate. Alignment is a
        # ranking/confluence bonus only and cannot turn 79 into a trade.
        candidates = tuple(
            replace(candidate, score=min(100.0, candidate.score + self._alignment_bonus(candidate, context)))
            for candidate in raw_candidates
        )
        eligible = [
            candidate
            for raw, candidate in zip(raw_candidates, candidates)
            if raw.eligible and raw.score >= self.minimum_score
        ]
        if not eligible:
            return StrategySelection(None, candidates, self.minimum_score)

        eligible.sort(key=lambda item: (-item.score, item.strategy))
        winner = eligible[0]

        opposing = [candidate for candidate in eligible[1:] if candidate.direction != winner.direction]
        if opposing and winner.score - opposing[0].score < 5.0:
            return StrategySelection(None, candidates, self.minimum_score)
        return StrategySelection(winner, candidates, self.minimum_score)
