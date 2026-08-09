from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class StrategyContext:
    """Broker-independent inputs supplied to a strategy."""

    pair: str
    regime: str
    bars: Mapping[str, Sequence[Any]]
    current_price: float


@dataclass(frozen=True)
class StrategyResult:
    """A deterministic strategy candidate; it is not an executable signal."""

    strategy: str
    direction: str
    score: float
    eligible: bool
    trigger: str
    invalidation: str
    evidence: tuple[str, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.direction not in {"BUY", "SELL", "NO_TRADE"}:
            raise ValueError("direction must be BUY, SELL, or NO_TRADE")
        if not 0 <= self.score <= 100:
            raise ValueError("score must be between 0 and 100")
        if self.eligible and self.direction == "NO_TRADE":
            raise ValueError("an eligible candidate cannot have NO_TRADE direction")


class Strategy(Protocol):
    name: str
    suitable_regimes: frozenset[str]

    def evaluate(self, context: StrategyContext) -> StrategyResult:
        """Evaluate the current market without placing or sizing an order."""
        ...
