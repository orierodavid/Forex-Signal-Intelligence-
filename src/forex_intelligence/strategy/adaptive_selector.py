from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .base import Strategy, StrategyContext, StrategyResult
from .strategies import DEFAULT_STRATEGIES


@dataclass(frozen=True)
class StrategyProfile:
    """Out-of-sample performance profile for a pair/timeframe/regime bucket."""
    expectancy_r: float = 0.0
    win_rate: float = 0.0
    samples: int = 0

    @property
    def reliability(self) -> float:
        if self.samples <= 0:
            return 0.0
        return min(1.0, self.samples / 100.0)


@dataclass(frozen=True)
class AdaptiveSelection:
    selected: StrategyResult | None
    candidates: tuple[StrategyResult, ...]
    threshold: float
    status: str = "NO_TRADE"

    @property
    def direction(self) -> str:
        return self.selected.direction if self.selected else "NO_TRADE"


class AdaptiveStrategySelector:
    """Regime-gated, evidence-aware selector used for shadow comparison."""

    def __init__(self, strategies: tuple[Strategy, ...] = DEFAULT_STRATEGIES, minimum_score: float = 70.0, profiles: Mapping[tuple[str, str, str, str], StrategyProfile] | None = None) -> None:
        if not 0 <= minimum_score <= 100:
            raise ValueError("minimum_score must be between 0 and 100")
        self.strategies = tuple(strategies)
        self.minimum_score = minimum_score
        self.profiles = dict(profiles or {})

    @staticmethod
    def _m15_direction(context: StrategyContext) -> str | None:
        regime = context.regimes.get("M15", context.regime)
        if regime in {"STRONG_TREND_UP", "TREND_UP"}:
            return "BUY"
        if regime in {"STRONG_TREND_DOWN", "TREND_DOWN"}:
            return "SELL"
        return None

    @staticmethod
    def _regime_family(regime: str) -> str:
        if regime in {"STRONG_TREND_UP", "TREND_UP"}:
            return "TREND_UP"
        if regime in {"STRONG_TREND_DOWN", "TREND_DOWN"}:
            return "TREND_DOWN"
        if regime == "RANGE":
            return "RANGE"
        if regime == "HIGH_VOLATILITY":
            return "HIGH_VOLATILITY"
        return "TRANSITION"

    def _profile(self, context: StrategyContext, strategy: StrategyResult) -> StrategyProfile:
        m15 = context.regimes.get("M15", context.regime)
        key = (context.pair, "M15", self._regime_family(m15), strategy.strategy)
        return self.profiles.get(key, StrategyProfile())

    @staticmethod
    def _composite(candidate: StrategyResult, profile: StrategyProfile) -> float:
        evidence = max(-10.0, min(10.0, profile.expectancy_r * 8.0))
        return min(100.0, max(0.0, candidate.score + evidence * profile.reliability))

    @staticmethod
    def _status(score: float) -> str:
        if score >= 75.0:
            return "QUALIFIED"
        if score >= 70.0:
            return "RISK_NOT_VETTED"
        return "NO_TRADE"

    def evaluate(self, context: StrategyContext) -> AdaptiveSelection:
        m15 = context.regimes.get("M15", context.regime)
        if m15 == "UNTRADEABLE":
            return AdaptiveSelection(None, tuple(), self.minimum_score, "NO_TRADE")

        raw = tuple(strategy.evaluate(context) for strategy in self.strategies)
        direction = self._m15_direction(context)
        ranked: list[StrategyResult] = []

        for candidate in raw:
            # A result is rejected only when the strategy itself explicitly says it
            # is ineligible. An invalidation price/condition is not an invalid
            # result; it is part of the resulting trade definition.
            if not candidate.eligible:
                continue
            if direction is not None and candidate.direction != direction:
                continue
            profile = self._profile(context, candidate)
            score = self._composite(candidate, profile)
            if score < self.minimum_score:
                continue
            metadata = dict(candidate.metadata)
            metadata.update({"adaptive_score": score, "historical_expectancy_r": profile.expectancy_r, "historical_win_rate": profile.win_rate, "historical_samples": profile.samples})
            ranked.append(StrategyResult(strategy=candidate.strategy, direction=candidate.direction, score=score, eligible=candidate.eligible, trigger=candidate.trigger, invalidation=candidate.invalidation, evidence=candidate.evidence, metadata=metadata))

        ranked.sort(key=lambda c: (-c.score, c.strategy))
        if not ranked:
            return AdaptiveSelection(None, tuple(raw), self.minimum_score, "NO_TRADE")

        if direction is None and len(ranked) > 1:
            if ranked[0].direction != ranked[1].direction and ranked[0].score - ranked[1].score < 5.0:
                return AdaptiveSelection(None, tuple(ranked), self.minimum_score, "NO_TRADE")

        selected = ranked[0]
        return AdaptiveSelection(selected, tuple(ranked), self.minimum_score, self._status(selected.score))
