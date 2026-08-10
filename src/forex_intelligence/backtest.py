from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from forex_intelligence.strategy import StrategyContext, StrategySelector


@dataclass(frozen=True)
class Candle:
    timestamp: str
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class BacktestTrade:
    pair: str
    timestamp: str
    strategy: str
    direction: str
    score: float
    entry: float
    stop_loss: float
    take_profit: float
    outcome_r: float
    exit_timestamp: str | None = None
    entry_timestamp: str | None = None

    @property
    def risk_vetted(self) -> bool:
        return self.score >= 75.0

    @property
    def risk_status(self) -> str:
        return "VETTED" if self.risk_vetted else "RISK_NOT_VETTED"


@dataclass(frozen=True)
class BacktestReport:
    pair: str
    trades: tuple[BacktestTrade, ...]

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def wins(self) -> int:
        return sum(1 for trade in self.trades if trade.outcome_r > 0)

    @property
    def losses(self) -> int:
        return sum(1 for trade in self.trades if trade.outcome_r < 0)

    @property
    def win_rate(self) -> float:
        resolved = self.wins + self.losses
        return self.wins / resolved * 100 if resolved else 0.0

    @property
    def net_r(self) -> float:
        return sum(trade.outcome_r for trade in self.trades)

    @property
    def average_r(self) -> float:
        resolved = [trade.outcome_r for trade in self.trades if trade.outcome_r != 0]
        return sum(resolved) / len(resolved) if resolved else 0.0

    @property
    def profit_factor(self) -> float:
        gross_profit = sum(t.outcome_r for t in self.trades if t.outcome_r > 0)
        gross_loss = abs(sum(t.outcome_r for t in self.trades if t.outcome_r < 0))
        return gross_profit / gross_loss if gross_loss else float("inf") if gross_profit else 0.0

    @property
    def risk_not_vetted_trades(self) -> int:
        return sum(1 for trade in self.trades if not trade.risk_vetted)

    @property
    def max_drawdown_r(self) -> float:
        equity = peak = 0.0
        max_drawdown = 0.0
        for trade in self.trades:
            equity += trade.outcome_r
            peak = max(peak, equity)
            max_drawdown = max(max_drawdown, peak - equity)
        return max_drawdown

    @property
    def trades_per_day(self) -> float:
        if not self.trades:
            return 0.0
        dates = [datetime.fromisoformat(t.timestamp).date() for t in self.trades]
        days = (max(dates) - min(dates)).days + 1
        return len(self.trades) / max(days, 1)

    def by_strategy(self) -> dict[str, "BacktestReport"]:
        groups: dict[str, list[BacktestTrade]] = {}
        for trade in self.trades:
            groups.setdefault(trade.strategy, []).append(trade)
        return {name: BacktestReport(self.pair, tuple(items)) for name, items in groups.items()}


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


def _aggregate(bars: Sequence[Candle], size: int) -> tuple[Candle, ...]:
    """Aggregate consecutive M15 candles; caller must provide UTC-aligned data."""
    result: list[Candle] = []
    for index in range(0, len(bars), size):
        chunk = bars[index:index + size]
        if len(chunk) < size:
            break
        result.append(Candle(
            timestamp=chunk[-1].timestamp,
            open=chunk[0].open,
            high=max(c.high for c in chunk),
            low=min(c.low for c in chunk),
            close=chunk[-1].close,
        ))
    return tuple(result)


def _find_pending_entry(candles: Sequence[Candle], start: int, entry: float) -> int | None:
    for i in range(start, len(candles)):
        if candles[i].low <= entry <= candles[i].high:
            return i
    return None


def run_backtest(
    pair: str,
    m15_bars: Sequence[Candle],
    *,
    selector: StrategySelector | None = None,
    minimum_score: float = 70.0,
    reward_risk: float = 2.0,
    lookback: int = 120,
) -> BacktestReport:
    """Replay the strategy path without look-ahead bias.

    M15 is the decision timeframe. H1/H4 are built only from already-closed
    M15 candles. A signal creates a pending entry at its explicit entry price;
    the position is opened only when a subsequent M15 candle trades through
    that price. 70-74 remains RISK_NOT_VETTED and 75+ is VETTED.

    Once triggered, SL/TP are checked from the entry candle onward. If an OHLC
    candle touches both levels, SL wins conservatively because OHLC data cannot
    establish intrabar ordering.
    """
    if minimum_score < 70:
        raise ValueError("minimum_score must be at least 70")
    if reward_risk <= 0:
        raise ValueError("reward_risk must be positive")
    selector = selector or StrategySelector(minimum_score=minimum_score)
    m15 = tuple(m15_bars)
    h1 = _aggregate(m15, 4)
    h4 = _aggregate(m15, 16)
    trades: list[BacktestTrade] = []

    for i in range(max(lookback, 30), len(m15) - 1):
        closed_m15 = m15[:i]
        current = closed_m15[-1]
        m15_regime = _regime([c.close for c in closed_m15])
        completed_h1 = tuple(c for c in h1 if c.timestamp <= current.timestamp)
        completed_h4 = tuple(c for c in h4 if c.timestamp <= current.timestamp)
        context = StrategyContext(
            pair=pair,
            regime=m15_regime,
            bars={"M15": closed_m15, "H1": completed_h1, "H4": completed_h4},
            current_price=current.close,
            regimes={
                "M15": m15_regime,
                "H1": _regime([c.close for c in completed_h1]),
                "H4": _regime([c.close for c in completed_h4]),
            },
        )
        selection = selector.evaluate(context)
        candidate = selection.selected
        if candidate is None or candidate.score < minimum_score:
            continue

        # Signal price is the proposed/pending entry, not an assumed fill at
        # the next candle's open.
        entry = current.close
        recent = closed_m15[-5:]
        if candidate.direction == "BUY":
            stop = min(c.low for c in recent)
            distance = entry - stop
            if distance <= 0:
                continue
            target = entry + distance * reward_risk
        else:
            stop = max(c.high for c in recent)
            distance = stop - entry
            if distance <= 0:
                continue
            target = entry - distance * reward_risk

        entry_index = _find_pending_entry(m15, i + 1, entry)
        if entry_index is None:
            continue

        outcome: float | None = None
        exit_timestamp: str | None = None
        for future in m15[entry_index:]:
            if candidate.direction == "BUY":
                hit_stop = future.low <= stop
                hit_target = future.high >= target
            else:
                hit_stop = future.high >= stop
                hit_target = future.low <= target
            if hit_stop:
                outcome = -1.0
                exit_timestamp = future.timestamp
                break
            if hit_target:
                outcome = reward_risk
                exit_timestamp = future.timestamp
                break
        if outcome is None:
            continue

        trades.append(BacktestTrade(
            pair=pair,
            timestamp=current.timestamp,
            strategy=candidate.strategy,
            direction=candidate.direction,
            score=candidate.score,
            entry=entry,
            stop_loss=stop,
            take_profit=target,
            outcome_r=outcome,
            entry_timestamp=m15[entry_index].timestamp,
            exit_timestamp=exit_timestamp,
        ))

    return BacktestReport(pair=pair, trades=tuple(trades))
