from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .base import Strategy, StrategyContext, StrategyResult
from .entry_quality import gate_candidate
from .profile import StrategyProfile, load_strategy_profile
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
    """Select a strategy using current regime plus an optional validated profile.

    When a walk-forward profile exists, only the strategy assigned to the
    current pair/regime is eligible. A missing assignment means NO_TRADE rather
    than allowing strategy-shopping across the full strategy library.
    """

    def __init__(self, strategies: Iterable[Strategy] = DEFAULT_STRATEGIES,
                 minimum_score: float = 70.0, minimum_entry_quality: float = 55.0,
                 profile: StrategyProfile | None = None) -> None:
        if not 0 <= minimum_score <= 100:
            raise ValueError("minimum_score must be between 0 and 100")
        if not 0 <= minimum_entry_quality <= 100:
            raise ValueError("minimum_entry_quality must be between 0 and 100")
        self.strategies = tuple(strategies)
        self.minimum_score = minimum_score
        self.minimum_entry_quality = minimum_entry_quality
        self.profile = profile if profile is not None else load_strategy_profile()

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

    def _active_strategies(self, context: StrategyContext) -> tuple[Strategy, ...]:
        if self.profile is None:
            return self.strategies
        regime = context.regimes.get("M15", context.regime)
        assigned = self.profile.strategy_for(context.pair, regime)
        if not assigned:
            return ()
        return tuple(strategy for strategy in self.strategies if strategy.name.upper() == assigned.upper())

    def evaluate(self, context: StrategyContext) -> StrategySelection:
        active = self._active_strategies(context)
        gated = tuple(gate_candidate(context, strategy.evaluate(context), self.minimum_entry_quality) for strategy in active)
        candidates = tuple(
            StrategyResult(
                strategy=candidate.strategy,
                direction=candidate.direction,
                score=candidate.score,
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

        if primary_direction is None:
            by_score = sorted(eligible_pairs, key=lambda candidate: (-candidate.score, candidate.strategy))
            if len(by_score) > 1 and by_score[0].direction != by_score[1].direction:
                if by_score[0].score - by_score[1].score < 5.0:
                    return StrategySelection(None, candidates, self.minimum_score)
            winner = by_score[0]
        else:
            ranked = sorted(
                eligible_pairs,
                key=lambda candidate: (-(candidate.score + self._alignment_bonus(candidate, context)), candidate.strategy),
            )
            winner = ranked[0]

        winner_score = min(100.0, winner.score + (self._alignment_bonus(winner, context) if primary_direction is not None else 0.0))
        selected = StrategyResult(
            strategy=winner.strategy,
            direction=winner.direction,
            score=winner_score,
            eligible=winner.eligible,
            trigger=winner.trigger,
            invalidation=winner.invalidation,
            evidence=winner.evidence,
            metadata=winner.metadata,
        )
        return StrategySelection(selected, candidates, self.minimum_score)
