"""Leakage-safe walk-forward evidence for current vs adaptive selection."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from forex_intelligence.adaptive_selector import (
    AdaptiveCandidate,
    AdaptiveStrategySelector,
    Direction,
    HistoricalEdge,
    MarketState,
    Regime,
)
from forex_intelligence.market_data.models import Bar
from forex_intelligence.strategy.base import StrategyContext, StrategyResult
from forex_intelligence.strategy.selector import StrategySelector
from forex_intelligence.strategy.strategies import DEFAULT_STRATEGIES


@dataclass(frozen=True)
class EvidenceTrade:
    pair: str
    signal_index: int
    strategy: str
    direction: str
    score: float
    entry: float
    stop_loss: float
    take_profit: float
    outcome_r: float
    entry_index: int
    exit_index: int
    risk_status: str
    regime: str = "TRANSITION"


@dataclass(frozen=True)
class EvidenceReport:
    selector: str
    trades: tuple[EvidenceTrade, ...]

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def wins(self) -> int:
        return sum(t.outcome_r > 0 for t in self.trades)

    @property
    def win_rate(self) -> float:
        return self.wins / self.total_trades * 100.0 if self.trades else 0.0

    @property
    def net_r(self) -> float:
        return sum(t.outcome_r for t in self.trades)

    @property
    def average_r(self) -> float:
        return self.net_r / self.total_trades if self.trades else 0.0

    @property
    def profit_factor(self) -> float:
        wins = sum(t.outcome_r for t in self.trades if t.outcome_r > 0)
        losses = abs(sum(t.outcome_r for t in self.trades if t.outcome_r < 0))
        return wins / losses if losses else (float("inf") if wins else 0.0)

    @property
    def max_drawdown_r(self) -> float:
        equity = peak = drawdown = 0.0
        for trade in self.trades:
            equity += trade.outcome_r
            peak = max(peak, equity)
            drawdown = max(drawdown, peak - equity)
        return drawdown

    @property
    def risk_not_vetted(self) -> int:
        return sum(t.risk_status == "RISK_NOT_VETTED" for t in self.trades)

    def by_strategy(self) -> dict[str, "EvidenceReport"]:
        groups: dict[str, list[EvidenceTrade]] = {}
        for trade in self.trades:
            groups.setdefault(trade.strategy, []).append(trade)
        return {name: EvidenceReport(self.selector, tuple(items)) for name, items in groups.items()}

    def by_regime(self) -> dict[str, "EvidenceReport"]:
        groups: dict[str, list[EvidenceTrade]] = {}
        for trade in self.trades:
            groups.setdefault(trade.regime, []).append(trade)
        return {name: EvidenceReport(self.selector, tuple(items)) for name, items in groups.items()}


def _regime(closes: Sequence[float]) -> Regime:
    if len(closes) < 20:
        return Regime.TRANSITION
    a = sum(closes[-20:-10]) / 10.0
    b = sum(closes[-10:]) / 10.0
    change = (b - a) / max(abs(a), 1e-12)
    if change > 0.0015:
        return Regime.TREND_UP
    if change < -0.0015:
        return Regime.TREND_DOWN
    return Regime.RANGE


def _aggregate(m15: Sequence[Bar], size: int) -> tuple[Bar, ...]:
    out: list[Bar] = []
    for i in range(0, len(m15), size):
        chunk = m15[i:i + size]
        if len(chunk) < size:
            break
        out.append(Bar(symbol=chunk[-1].symbol, timeframe=chunk[-1].timeframe, timestamp=chunk[-1].timestamp,
                       open=chunk[0].open, high=max(x.high for x in chunk), low=min(x.low for x in chunk),
                       close=chunk[-1].close, quality="REAL"))
    return tuple(out)


def _context(pair: str, m15: Sequence[Bar], index: int) -> StrategyContext:
    closed = tuple(m15[:index])
    h1 = _aggregate(closed, 4)
    h4 = _aggregate(closed, 16)
    m15_regime = _regime([b.close for b in closed])
    return StrategyContext(
        pair=pair,
        regime=m15_regime.value,
        bars={"M15": closed, "H1": h1, "H4": h4},
        current_price=closed[-1].close,
        regimes={"M15": m15_regime.value, "H1": _regime([b.close for b in h1]).value,
                 "H4": _regime([b.close for b in h4]).value},
    )


def _trade_outcome(bars: Sequence[Bar], start: int, direction: str, entry: float, stop: float, target: float) -> tuple[int, int, float] | None:
    entry_index = next((i for i in range(start, len(bars)) if bars[i].low <= entry <= bars[i].high), None)
    if entry_index is None:
        return None
    for i in range(entry_index, len(bars)):
        bar = bars[i]
        if direction == "BUY":
            if bar.low <= stop:
                return entry_index, i, -1.0
            if bar.high >= target:
                return entry_index, i, 2.0
        else:
            if bar.high >= stop:
                return entry_index, i, -1.0
            if bar.low <= target:
                return entry_index, i, 2.0
    return None


def _levels(bars: Sequence[Bar], index: int, entry: float, direction: str) -> tuple[float, float] | None:
    recent = bars[index - 5:index]
    if len(recent) < 5:
        return None
    if direction == "BUY":
        stop = min(x.low for x in recent)
        risk = entry - stop
        return (stop, entry + 2.0 * risk) if risk > 0 else None
    stop = max(x.high for x in recent)
    risk = stop - entry
    return (stop, entry - 2.0 * risk) if risk > 0 else None


def _candidate(strategy, context: StrategyContext) -> StrategyResult | None:
    result = strategy.evaluate(context)
    return result if result.eligible and result.direction in {"BUY", "SELL"} and result.score >= 70 else None


def _training_profiles(pair: str, bars: Sequence[Bar], start: int, end: int) -> dict[tuple[str, str], HistoricalEdge]:
    """Evaluate every strategy independently on the prior training window.

    This avoids the previous circular error where adaptive historical edge was
    learned from trades already selected by the current selector. No test bar is
    included in these profiles.
    """
    outcomes: dict[tuple[str, str], list[float]] = {}
    for i in range(max(start, 30), min(end, len(bars) - 1)):
        context = _context(pair, bars, i)
        regime = context.regimes.get("M15", context.regime)
        for strategy in DEFAULT_STRATEGIES:
            candidate = _candidate(strategy, context)
            if candidate is None:
                continue
            levels = _levels(bars, i, context.current_price, candidate.direction)
            if levels is None:
                continue
            outcome = _trade_outcome(bars, i + 1, candidate.direction, context.current_price, *levels)
            if outcome is None:
                continue
            _, _, result_r = outcome
            outcomes.setdefault((regime, candidate.strategy), []).append(result_r)

    profiles: dict[tuple[str, str], HistoricalEdge] = {}
    for key, values in outcomes.items():
        n = len(values)
        avg_r = sum(values) / n
        win_rate = sum(v > 0 for v in values) / n
        gross_profit = sum(v for v in values if v > 0)
        gross_loss = abs(sum(v for v in values if v < 0))
        pf = gross_profit / gross_loss if gross_loss else None
        profiles[key] = HistoricalEdge(n, avg_r, win_rate, pf)
    return profiles


def _adaptive_candidates(context: StrategyContext, profiles: dict[tuple[str, str], HistoricalEdge]) -> tuple[AdaptiveCandidate, ...]:
    result: list[AdaptiveCandidate] = []
    regime = context.regimes.get("M15", context.regime)
    for strategy in DEFAULT_STRATEGIES:
        candidate = _candidate(strategy, context)
        if candidate is None:
            continue
        result.append(AdaptiveCandidate(
            strategy=candidate.strategy,
            direction=Direction(candidate.direction),
            base_score=candidate.score,
            setup_quality=candidate.score,
            entry_quality=candidate.score,
            risk_reward_quality=candidate.score,
            historical_edge=profiles.get((regime, candidate.strategy)),
            trigger=candidate.trigger,
            invalidation=candidate.invalidation,
            evidence=candidate.evidence,
            metadata=candidate.metadata,
        ))
    return tuple(result)


def _adaptive_state(context: StrategyContext) -> MarketState:
    return MarketState(pair=context.pair, timeframe="M15",
                       regime=Regime(context.regimes.get("M15", context.regime)),
                       h1_regime=Regime(context.regimes.get("H1", "TRANSITION")),
                       h4_regime=Regime(context.regimes.get("H4", "TRANSITION")))


def run_walk_forward(pair: str, m15_bars: Sequence[Bar], *, train_bars: int = 1000,
                     test_bars: int = 250, lookback: int = 120,
                     minimum_score: float = 70.0) -> tuple[EvidenceReport, EvidenceReport]:
    """Compare selectors with a strict rolling train/test boundary."""
    bars = tuple(m15_bars)
    current_selector = StrategySelector(minimum_score=minimum_score)
    adaptive_selector = AdaptiveStrategySelector(minimum_score=minimum_score)
    current_trades: list[EvidenceTrade] = []
    adaptive_trades: list[EvidenceTrade] = []

    test_start = max(train_bars, lookback)
    while test_start < len(bars) - 1:
        test_end = min(test_start + test_bars, len(bars) - 1)
        train_start = max(lookback, test_start - train_bars)
        profiles = _training_profiles(pair, bars, train_start, test_start)

        for i in range(test_start, test_end):
            context = _context(pair, bars, i)
            regime = context.regimes.get("M15", context.regime)

            current = current_selector.evaluate(context).selected
            if current and current.score >= minimum_score:
                levels = _levels(bars, i, context.current_price, current.direction)
                if levels:
                    outcome = _trade_outcome(bars, i + 1, current.direction, context.current_price, *levels)
                    if outcome:
                        ei, xi, r = outcome
                        current_trades.append(EvidenceTrade(pair, i, current.strategy, current.direction, current.score,
                                                            context.current_price, levels[0], levels[1], r, ei, xi,
                                                            "VETTED" if current.score >= 75 else "RISK_NOT_VETTED", regime))

            adaptive = adaptive_selector.evaluate(_adaptive_state(context), _adaptive_candidates(context, profiles)).selected
            if adaptive and adaptive.composite_score >= minimum_score:
                direction = adaptive.direction.value
                levels = _levels(bars, i, context.current_price, direction)
                if levels:
                    outcome = _trade_outcome(bars, i + 1, direction, context.current_price, *levels)
                    if outcome:
                        ei, xi, r = outcome
                        adaptive_trades.append(EvidenceTrade(pair, i, adaptive.strategy, direction, adaptive.composite_score,
                                                             context.current_price, levels[0], levels[1], r, ei, xi,
                                                             "VETTED" if adaptive.composite_score >= 75 else "RISK_NOT_VETTED", regime))
        test_start = test_end

    return EvidenceReport("CURRENT", tuple(current_trades)), EvidenceReport("ADAPTIVE", tuple(adaptive_trades))
