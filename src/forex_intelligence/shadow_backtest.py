"""Evidence runner comparing the current and adaptive selectors on identical history."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from forex_intelligence.adaptive_selector import AdaptiveCandidate, AdaptiveStrategySelector, Direction, HistoricalEdge, MarketState, Regime
from forex_intelligence.backtest import BacktestReport, BacktestTrade, Candle
from forex_intelligence.strategy import StrategyContext, StrategySelector


@dataclass(frozen=True)
class SelectorComparison:
    pair: str
    current: BacktestReport
    adaptive: BacktestReport

    @property
    def current_expectancy_r(self) -> float:
        return self.current.average_r

    @property
    def adaptive_expectancy_r(self) -> float:
        return self.adaptive.average_r

    @property
    def adaptive_improvement_r(self) -> float:
        return self.adaptive_expectancy_r - self.current_expectancy_r


@dataclass(frozen=True)
class ShadowResult:
    comparisons: tuple[SelectorComparison, ...]

    @property
    def current_trades(self) -> int:
        return sum(c.current.total_trades for c in self.comparisons)

    @property
    def adaptive_trades(self) -> int:
        return sum(c.adaptive.total_trades for c in self.comparisons)

    @property
    def current_net_r(self) -> float:
        return sum(c.current.net_r for c in self.comparisons)

    @property
    def adaptive_net_r(self) -> float:
        return sum(c.adaptive.net_r for c in self.comparisons)

    @property
    def adaptive_improvement_r(self) -> float:
        return self.adaptive_net_r - self.current_net_r


def _regime(closes: Sequence[float]) -> str:
    if len(closes) < 20:
        return "TRANSITION"
    first = sum(closes[-20:-10]) / 10
    second = sum(closes[-10:]) / 10
    change = (second - first) / max(abs(first), 1e-12)
    if change > 0.0015:
        return "TREND_UP"
    if change < -0.0015:
        return "TREND_DOWN"
    return "RANGE"


def _market_state(pair: str, m15: Sequence[Candle], index: int) -> MarketState:
    closed = m15[:index]
    m15_regime = _regime([c.close for c in closed])
    h1 = tuple(closed[::4])
    h4 = tuple(closed[::16])
    return MarketState(
        pair=pair,
        timeframe="M15",
        regime=Regime(m15_regime),
        h1_regime=Regime(_regime([c.close for c in h1])),
        h4_regime=Regime(_regime([c.close for c in h4])),
    )


def _context(pair: str, m15: Sequence[Candle], index: int) -> StrategyContext:
    closed = m15[:index]
    h1 = tuple(c for i, c in enumerate(closed) if (i + 1) % 4 == 0)
    h4 = tuple(c for i, c in enumerate(closed) if (i + 1) % 16 == 0)
    return StrategyContext(
        pair=pair,
        regime=_regime([c.close for c in closed]),
        bars={"M15": closed, "H1": h1, "H4": h4},
        current_price=closed[-1].close,
        regimes={
            "M15": _regime([c.close for c in closed]),
            "H1": _regime([c.close for c in h1]),
            "H4": _regime([c.close for c in h4]),
        },
    )


def _adaptive_candidates(context: StrategyContext, current: StrategySelector) -> tuple[AdaptiveCandidate, ...]:
    raw = tuple(strategy.evaluate(context) for strategy in current.strategies)
    result: list[AdaptiveCandidate] = []
    for candidate in raw:
        if not candidate.eligible or candidate.direction == "NO_TRADE":
            continue
        result.append(
            AdaptiveCandidate(
                strategy=candidate.strategy,
                direction=Direction(candidate.direction),
                base_score=candidate.score,
                setup_quality=candidate.score,
                entry_quality=candidate.score,
                risk_reward_quality=candidate.score,
                historical_edge=HistoricalEdge(0, 0.0, 0.0),
                trigger=candidate.trigger,
                invalidation=candidate.invalidation,
                evidence=candidate.evidence,
                metadata=candidate.metadata,
            )
        )
    return tuple(result)


def _replay_trade(pair: str, signal: Candle, future: Sequence[Candle], strategy: str, direction: str, score: float, reward_risk: float) -> BacktestTrade | None:
    recent_low = min(c.low for c in future[:5]) if future else signal.low
    recent_high = max(c.high for c in future[:5]) if future else signal.high
    entry = signal.close
    if direction == "BUY":
        stop = recent_low
        risk = entry - stop
        if risk <= 0:
            return None
        target = entry + risk * reward_risk
    else:
        stop = recent_high
        risk = stop - entry
        if risk <= 0:
            return None
        target = entry - risk * reward_risk
    for candle in future:
        if direction == "BUY":
            hit_stop, hit_target = candle.low <= stop, candle.high >= target
        else:
            hit_stop, hit_target = candle.high >= stop, candle.low <= target
        if hit_stop:
            outcome = -1.0
            return BacktestTrade(pair, signal.timestamp, strategy, direction, score, entry, stop, target, outcome, candle.timestamp, candle.timestamp)
        if hit_target:
            outcome = reward_risk
            return BacktestTrade(pair, signal.timestamp, strategy, direction, score, entry, stop, target, outcome, candle.timestamp, candle.timestamp)
    return None


def run_shadow_backtest(pair: str, m15_bars: Sequence[Candle], *, minimum_score: float = 70.0, reward_risk: float = 2.0, lookback: int = 120) -> SelectorComparison:
    """Compare selectors without look-ahead using the same closed M15 history.

    This is deliberately an evidence runner, not a live-trading path. Historical
    edge is disabled here until a walk-forward training window is supplied, so
    the adaptive selector cannot accidentally learn from the test period.
    """
    current_selector = StrategySelector(minimum_score=minimum_score)
    adaptive_selector = AdaptiveStrategySelector(minimum_score=minimum_score, qualified_score=75.0)
    current_trades: list[BacktestTrade] = []
    adaptive_trades: list[BacktestTrade] = []
    bars = tuple(m15_bars)

    for i in range(max(lookback, 30), len(bars) - 6):
        context = _context(pair, bars, i)
        current = current_selector.evaluate(context)
        adaptive = adaptive_selector.evaluate(_market_state(pair, bars, i), _adaptive_candidates(context, current_selector))
        future = bars[i + 1 : i + 31]

        if current.selected is not None and current.selected.score >= minimum_score:
            trade = _replay_trade(pair, bars[i], future, current.selected.strategy, current.selected.direction, current.selected.score, reward_risk)
            if trade:
                current_trades.append(trade)
        if adaptive.selected is not None and adaptive.score >= minimum_score:
            trade = _replay_trade(pair, bars[i], future, adaptive.selected.strategy, adaptive.selected.direction.value, adaptive.score, reward_risk)
            if trade:
                adaptive_trades.append(trade)

    return SelectorComparison(pair, BacktestReport(pair, tuple(current_trades)), BacktestReport(pair, tuple(adaptive_trades)))
