from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ConditionalEvidence:
    """Forward-tested evidence for one narrow market condition.

    Training performance is intentionally not part of the promotion decision.
    A condition must repeatedly survive unseen windows before it can influence
    the live selector.
    """

    pair: str
    strategy: str
    regime: str
    session: str
    volatility: str
    reward_risk: float
    windows: int
    positive_windows: int
    median_test_expectancy_r: float
    median_profit_factor: float
    max_drawdown_r: float
    promoted: bool = False

    @property
    def stability(self) -> float:
        return self.positive_windows / self.windows if self.windows else 0.0

    def qualifies(self) -> bool:
        """Return whether this condition meets the conservative promotion gate."""
        return (
            self.windows >= 4
            and self.positive_windows >= 3
            and self.stability >= 0.75
            and self.median_test_expectancy_r > 0.10
            and self.median_profit_factor > 1.15
            and self.max_drawdown_r <= 12.0
        )


class ConditionalStrategyRegistry:
    """Evidence registry used in shadow mode before live promotion.

    The registry is fail-closed: entries only become eligible when their
    forward-test statistics satisfy ``qualifies``. The explicit ``promoted``
    flag is retained as a second human/audit gate; statistics alone never
    silently activate a condition.
    """

    def __init__(self, evidence: Iterable[ConditionalEvidence] = ()) -> None:
        self._evidence = tuple(evidence)

    @property
    def evidence(self) -> tuple[ConditionalEvidence, ...]:
        return self._evidence

    def matching(self, pair: str, regime: str, session: str, volatility: str) -> tuple[ConditionalEvidence, ...]:
        return tuple(
            e for e in self._evidence
            if e.pair == pair
            and e.regime == regime
            and e.session == session
            and e.volatility == volatility
            and e.promoted
            and e.qualifies()
        )

    def best(self, pair: str, regime: str, session: str, volatility: str) -> ConditionalEvidence | None:
        matches = self.matching(pair, regime, session, volatility)
        return max(
            matches,
            key=lambda e: (e.median_test_expectancy_r, e.median_profit_factor, e.stability),
        ) if matches else None

    @staticmethod
    def should_promote(
        *,
        windows: int,
        positive_windows: int,
        median_test_expectancy_r: float,
        median_profit_factor: float,
        max_drawdown_r: float,
    ) -> bool:
        return (
            windows >= 4
            and positive_windows >= 3
            and positive_windows / windows >= 0.75
            and median_test_expectancy_r > 0.10
            and median_profit_factor > 1.15
            and max_drawdown_r <= 12.0
        )
