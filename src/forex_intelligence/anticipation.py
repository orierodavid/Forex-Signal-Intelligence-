from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Mapping, Sequence, Any

from forex_intelligence.strategy.base import StrategyResult


class AnticipationState(str, Enum):
    WATCHING = "WATCHING"
    READY = "READY"
    TRIGGERED = "TRIGGERED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class AnticipatedSetup:
    setup_id: str
    pair: str
    direction: str
    strategy: str
    state: AnticipationState
    current_price: float
    potential_entry_low: float
    potential_entry_high: float
    trigger: str
    invalidation: str
    expires_at: datetime
    score: float
    evidence: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.direction not in {"BUY", "SELL"}:
            raise ValueError("direction must be BUY or SELL")
        if self.potential_entry_low > self.potential_entry_high:
            raise ValueError("potential entry range is inverted")
        if not 0 <= self.score <= 100:
            raise ValueError("score must be between 0 and 100")


class AnticipationEngine:
    """Creates and transitions developing setups without executing trades."""

    def __init__(self, expiry_minutes: int = 60) -> None:
        if expiry_minutes <= 0:
            raise ValueError("expiry_minutes must be positive")
        self.expiry_minutes = expiry_minutes

    @staticmethod
    def _close(bar: Any) -> float:
        return float(bar["close"] if isinstance(bar, Mapping) else getattr(bar, "close"))

    @staticmethod
    def _high(bar: Any) -> float:
        return float(bar["high"] if isinstance(bar, Mapping) else getattr(bar, "high"))

    @staticmethod
    def _low(bar: Any) -> float:
        return float(bar["low"] if isinstance(bar, Mapping) else getattr(bar, "low"))

    def create_watch(self, *, setup_id: str, candidate: StrategyResult, pair: str,
                     current_price: float, now: datetime | None = None) -> AnticipatedSetup | None:
        if not candidate.eligible or candidate.direction == "NO_TRADE":
            return None
        now = now or datetime.now(timezone.utc)
        metadata = candidate.metadata
        low = float(metadata.get("entry_low", current_price))
        high = float(metadata.get("entry_high", current_price))
        state = AnticipationState.READY if low <= current_price <= high else AnticipationState.WATCHING
        return AnticipatedSetup(
            setup_id=setup_id,
            pair=pair,
            direction=candidate.direction,
            strategy=candidate.strategy,
            state=state,
            current_price=current_price,
            potential_entry_low=low,
            potential_entry_high=high,
            trigger=candidate.trigger,
            invalidation=candidate.invalidation,
            expires_at=now + timedelta(minutes=self.expiry_minutes),
            score=candidate.score,
            evidence=candidate.evidence,
        )

    def transition(self, setup: AnticipatedSetup, *, current_price: float,
                   trigger_confirmed: bool, invalidated: bool = False,
                   now: datetime | None = None) -> AnticipatedSetup:
        now = now or datetime.now(timezone.utc)
        if setup.state in {AnticipationState.INVALIDATED, AnticipationState.EXPIRED}:
            return setup
        if invalidated:
            state = AnticipationState.INVALIDATED
        elif now >= setup.expires_at:
            state = AnticipationState.EXPIRED
        elif trigger_confirmed:
            state = AnticipationState.TRIGGERED
        elif setup.potential_entry_low <= current_price <= setup.potential_entry_high:
            state = AnticipationState.READY
        else:
            state = AnticipationState.WATCHING
        return AnticipatedSetup(
            setup_id=setup.setup_id, pair=setup.pair, direction=setup.direction,
            strategy=setup.strategy, state=state, current_price=current_price,
            potential_entry_low=setup.potential_entry_low,
            potential_entry_high=setup.potential_entry_high,
            trigger=setup.trigger, invalidation=setup.invalidation,
            expires_at=setup.expires_at, score=setup.score, evidence=setup.evidence,
        )
