from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .base import Strategy, StrategyContext, StrategyResult
from .entry_quality import gate_candidate
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
    """Select the best M15 strategy only after an independent entry-quality gate."""

    def __init__(self, strategies: Iterable[Strategy] = DEFAULT_STRATEGIES, minimum_score: float = 70.0, minimum_entry_quality: float = 55.0) -> None:
        if not 0 <= minimum_score <= 100:
            raise ValueError("minimum_score must be between 0 and 100")
        if not 0 <= minimum_entry_quality <= 100:
            raise ValueError("minimum_entry_quality must be between 0 and 100")
        self.strategies = tuple(strategies)
        self.minimum_score = minimum_score
        self.minimum_entry_quality = minimum_entry_quality

    @staticmethod
    def _primary_direction(context: StrategyContext) -> str | None:
        regime = context.regimes.get("M15", context.regime)
        if regime in {"STRONG_TREND_UP", "TREND_UP"}:
            return "BUY"
        if regime in {"STRONG_TREND_DOWN", "TREND_DOWN"}:
            return "SELL"
        return None

    @staticmethod
    def _alignment_bonus(candidate: StrategyResult, context: StrategyContext) -> float:
        if candidate.direction not in {"BUY", "SELL"}:
            return 0.0
        bonus = 0.0
        h4 = context.regimes.get("H4", "")
        h1 = context.regimes.get("H1", context.regime)
        aligned = {"STRONG_TREND_UP", "TREND_UP"} if candidate.direction == "BUY" else {"STRONG_TREND_DOWN", "TREND_DOWN"}
        if h4 in aligned:
            bonus += 3.0
        if h1 in aligned:
            bonus += 2.0
        return bonus

    def evaluate(self, context: StrategyContext) -> StrategySelection:
        gated = tuple(gate_candidate(context, strategy.evaluate(context), self.minimum_entry_quality) for strategy in self.strategies)
        candidates = tuple(
            StrategyResult(
                strategy=candidate.strategy,
                direction=candidate.direction,
                score=(candidate.score if not context.bars.get("M15") else min(100.0, candidate.score + self._alignment_bonus(candidate, context))) if candidate.eligible else candidate.score,
                eligible=candidate.eligible,
                trigger=candidate.trigger,
                invalidation=candidate.invalidation,
                evidence=candidate.evidence,
                metadata=candidate.metadata,
            )
            for candidate in gated
        )

        primary_direction = self._primary_direction(context)
        eligible_pairs = [
            candidate for candidate in candidates
            if candidate.eligible
            and candidate.score >= self.minimum_score
            and (primary_direction is None or candidate.direction == primary_direction)
        ]
        if not eligible_pairs:
            return StrategySelection(None, candidates, self.minimum_score)

        eligible_pairs.sort(key=lambda candidate: (-candidate.score, candidate.strategy))
        winner = eligible_pairs[0]
        opposing = [candidate for candidate in eligible_pairs[1:] if candidate.direction != winner.direction]
        if primary_direction is None and opposing and winner.score - opposing[0].score < 5.0:
            return StrategySelection(None, candidates, self.minimum_score)
        return StrategySelection(winner, candidates, self.minimum_score)
