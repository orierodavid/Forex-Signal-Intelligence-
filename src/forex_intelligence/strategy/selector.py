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
    """Select the single best strategy for an M15 trading decision.

    M15 is the primary decision timeframe. H1 and H4 are confirmation layers
    that can strengthen the ranking of an already-qualified M15 setup, but
    they do not replace the M15 market direction.

    A candidate must score at least 75/100 on its own. When M15 is clearly
    directional, strategies fighting that M15 direction are not eligible for
    selection. This prevents a higher-scoring opposing strategy from winning
    solely because its raw score is numerically larger.

    H1/H4 confluence bonuses are used only for ranking and never manufacture
    eligibility. Opposing candidates in neutral M15 regimes remain ambiguous
    when their raw scores are too close.
    """

    def __init__(self, strategies: Iterable[Strategy] = DEFAULT_STRATEGIES, minimum_score: float = 75.0) -> None:
        if not 0 <= minimum_score <= 100:
            raise ValueError("minimum_score must be between 0 and 100")
        self.strategies = tuple(strategies)
        self.minimum_score = minimum_score

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
        candidates = tuple(
            replace(candidate, score=min(100.0, candidate.score + self._alignment_bonus(candidate, context)))
            for candidate in raw_candidates
        )

        primary_direction = self._primary_direction(context)
        eligible_pairs = [
            (raw, ranked)
            for raw, ranked in zip(raw_candidates, candidates)
            if raw.eligible
            and raw.score >= self.minimum_score
            and (primary_direction is None or raw.direction == primary_direction)
        ]
        if not eligible_pairs:
            return StrategySelection(None, candidates, self.minimum_score)

        eligible_pairs.sort(key=lambda pair: (-pair[1].score, pair[1].strategy))
        winner_raw, winner = eligible_pairs[0]

        opposing = [
            (raw, ranked)
            for raw, ranked in eligible_pairs[1:]
            if ranked.direction != winner.direction
        ]
        # In neutral M15 regimes, use raw strategy scores for ambiguity. H1/H4
        # bonuses are confluence evidence, not evidence that should manufacture
        # a decisive edge over a genuinely competing opposing setup.
        if primary_direction is None and opposing and winner_raw.score - opposing[0][0].score < 5.0:
            return StrategySelection(None, candidates, self.minimum_score)
        return StrategySelection(winner, candidates, self.minimum_score)
