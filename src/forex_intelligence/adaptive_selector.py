"""Adaptive strategy selection based on market state, setup quality, and expectancy.

This module deliberately separates *strategy suitability* from the legacy 0-100
candidate score. It is a deterministic production-safe selector: historical
performance is an optional input and is never allowed to override current
market structure or create a trade from missing evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from typing import Mapping, Sequence


class Regime(str, Enum):
    STRONG_TREND_UP = "STRONG_TREND_UP"
    TREND_UP = "TREND_UP"
    RANGE = "RANGE"
    TRANSITION = "TRANSITION"
    TREND_DOWN = "TREND_DOWN"
    STRONG_TREND_DOWN = "STRONG_TREND_DOWN"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    UNTRADEABLE = "UNTRADEABLE"


class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class MarketState:
    pair: str
    timeframe: str = "M15"
    regime: Regime = Regime.UNTRADEABLE
    h1_regime: Regime = Regime.UNTRADEABLE
    h4_regime: Regime = Regime.UNTRADEABLE
    volatility_percentile: float | None = None
    session: str | None = None
    trend_alignment: float = 0.0
    structure_quality: float = 0.0
    spread_quality: float = 100.0


@dataclass(frozen=True)
class HistoricalEdge:
    """Out-of-sample conditional performance for a strategy/state bucket."""

    samples: int
    expectancy_r: float
    win_rate: float
    profit_factor: float | None = None


@dataclass(frozen=True)
class AdaptiveCandidate:
    strategy: str
    direction: Direction
    base_score: float
    setup_quality: float
    entry_quality: float
    risk_reward_quality: float
    historical_edge: HistoricalEdge | None = None
    trigger: str = "confirmed"
    invalidation: str = "invalidated"
    evidence: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def suitability(self) -> float:
        """Current-state strategy suitability, independent of trade score."""
        return self._clamp(
            0.35 * self.setup_quality
            + 0.25 * self.entry_quality
            + 0.20 * self.risk_reward_quality
            + 0.20 * self._historical_quality()
        )

    @property
    def composite_score(self) -> float:
        """Decision score used for ranking eligible candidates."""
        # Base score remains visible for compatibility, but current entry and
        # conditional evidence have material weight so a stale high score cannot
        # win on its own.
        return self._clamp(
            0.40 * self.base_score
            + 0.20 * self.setup_quality
            + 0.15 * self.entry_quality
            + 0.10 * self.risk_reward_quality
            + 0.15 * self._historical_quality()
        )

    def _historical_quality(self) -> float:
        if not self.historical_edge or self.historical_edge.samples < 30:
            return 50.0
        expectancy = self.historical_edge.expectancy_r
        # Map a useful but deliberately conservative expectancy range to 0-100.
        quality = 50.0 + expectancy * 50.0
        if self.historical_edge.profit_factor is not None:
            quality += (self.historical_edge.profit_factor - 1.0) * 10.0
        return self._clamp(quality)

    @staticmethod
    def _clamp(value: float) -> float:
        if not isfinite(value):
            return 0.0
        return max(0.0, min(100.0, value))


@dataclass(frozen=True)
class Selection:
    selected: AdaptiveCandidate | None
    status: str
    score: float = 0.0
    reason: str = ""
    eligible_candidates: tuple[AdaptiveCandidate, ...] = ()


REGIME_FAMILIES: dict[Regime, frozenset[str]] = {
    Regime.STRONG_TREND_UP: frozenset({"TREND_PULLBACK", "MOMENTUM_CONTINUATION"}),
    Regime.TREND_UP: frozenset({"TREND_PULLBACK", "MOMENTUM_CONTINUATION", "BREAKOUT_RETEST"}),
    Regime.RANGE: frozenset({"SUPPORT_RESISTANCE_REJECTION", "MEAN_REVERSION"}),
    Regime.TRANSITION: frozenset({"BREAKOUT_RETEST", "LIQUIDITY_SWEEP_REVERSAL"}),
    Regime.TREND_DOWN: frozenset({"TREND_PULLBACK", "MOMENTUM_CONTINUATION", "BREAKOUT_RETEST"}),
    Regime.STRONG_TREND_DOWN: frozenset({"TREND_PULLBACK", "MOMENTUM_CONTINUATION"}),
    Regime.HIGH_VOLATILITY: frozenset({"BREAKOUT_RETEST", "MOMENTUM_CONTINUATION", "LIQUIDITY_SWEEP_REVERSAL"}),
    Regime.LOW_VOLATILITY: frozenset({"SUPPORT_RESISTANCE_REJECTION", "MEAN_REVERSION"}),
    Regime.UNTRADEABLE: frozenset(),
}


class AdaptiveStrategySelector:
    """Select the best current setup without forcing a trade."""

    def __init__(self, minimum_score: float = 70.0, qualified_score: float = 75.0):
        self.minimum_score = minimum_score
        self.qualified_score = qualified_score

    def evaluate(
        self,
        state: MarketState,
        candidates: Sequence[AdaptiveCandidate],
    ) -> Selection:
        if state.regime is Regime.UNTRADEABLE:
            return Selection(None, "NO_TRADE", reason="market is untradeable")

        allowed = REGIME_FAMILIES.get(state.regime, frozenset())
        if not allowed:
            return Selection(None, "NO_TRADE", reason="no strategy family is compatible with regime")

        alignment = self._directional_alignment(state)
        eligible: list[AdaptiveCandidate] = []
        for candidate in candidates:
            if candidate.strategy not in allowed:
                continue
            if candidate.base_score < self.minimum_score:
                continue
            if candidate.invalidation.lower() in {"invalidated", "invalid"}:
                continue
            # Current M15 direction is a gate, not a minor scoring factor.
            if alignment > 0.60 and candidate.direction is not Direction.BUY:
                continue
            if alignment < -0.60 and candidate.direction is not Direction.SELL:
                continue
            if state.spread_quality < 40.0:
                continue
            eligible.append(candidate)

        if not eligible:
            return Selection(None, "NO_TRADE", reason="no regime-compatible candidate passed gates")

        ranked = sorted(
            eligible,
            key=lambda c: (c.composite_score, c.suitability, c.setup_quality, c.entry_quality),
            reverse=True,
        )
        best = ranked[0]

        # Do not manufacture certainty when opposing candidates are close.
        if len(ranked) > 1:
            second = ranked[1]
            if second.direction is not best.direction and best.composite_score - second.composite_score < 5.0:
                return Selection(
                    None,
                    "NO_TRADE",
                    reason="opposing candidates are too close",
                    eligible_candidates=tuple(ranked),
                )

        status = "QUALIFIED" if best.composite_score >= self.qualified_score else "RISK_NOT_VETTED"
        return Selection(
            best,
            status,
            score=best.composite_score,
            reason="best regime-compatible candidate",
            eligible_candidates=tuple(ranked),
        )

    @staticmethod
    def _directional_alignment(state: MarketState) -> float:
        # H1/H4 strengthen M15; they do not replace it.
        m15 = 1.0 if state.regime in {Regime.TREND_UP, Regime.STRONG_TREND_UP} else -1.0 if state.regime in {Regime.TREND_DOWN, Regime.STRONG_TREND_DOWN} else 0.0
        h1 = 1.0 if state.h1_regime in {Regime.TREND_UP, Regime.STRONG_TREND_UP} else -1.0 if state.h1_regime in {Regime.TREND_DOWN, Regime.STRONG_TREND_DOWN} else 0.0
        h4 = 1.0 if state.h4_regime in {Regime.TREND_UP, Regime.STRONG_TREND_UP} else -1.0 if state.h4_regime in {Regime.TREND_DOWN, Regime.STRONG_TREND_DOWN} else 0.0
        return 0.60 * m15 + 0.25 * h1 + 0.15 * h4
