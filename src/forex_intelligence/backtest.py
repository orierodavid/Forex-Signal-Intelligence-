from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

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
        return self.wins / self.total_trades * 100 if self.total_trades else 0.0

    @property
    def net_r(self) -> float:
        return sum(trade.outcome_r for trade in self.trades)

    @property
    def profit_factor(self) -> float:
        gross_profit = sum(t.outcome_r for t in self.trades if t.outcome_r > 0)
        gross_loss = abs(sum(t.outcome_r for t in self.trades if t.outcome_r < 0))
        return gross_profit / gross_loss if gross_loss else float("inf") if gross_profit else 0.0


def _regime(closes: Sequence[float]) -> str:
    """Conservative regime proxy used only when replaying raw candles.

    The live pipeline supplies the production RegimeEngine. The backtester
    intentionally keeps this function small and deterministic so historical
    replay cannot accidentally use future candles.
    """
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


def run_backtest(
    pair: str,
    m15_bars: Sequence[Candle],
    *,
    selector: StrategySelector | None = None,
    minimum_score: float = 70.0,
    risk_score: float = 75.0,
    reward_risk: float = 2.0,
    lookback: int = 120,
) -> BacktestReport:
    """Replay the production strategy-selection concept without look-ahead.

    M15 is the decision timeframe. H1/H4 are built only from candles already
    closed at the decision point. A trade is entered on the next M15 bar's
    open, never on the same candle that generated the setup.

    Scores >= 70 are recorded as alerts. Scores >= 75 are marked normally
    qualified. The report retains the 70-74 trades so we can measure whether
    the risk-not-vetted band has useful predictive value.
    """
    selector = selector or StrategySelector(minimum_score=minimum_score)
    m15 = tuple(m15_bars)
    h1 = _aggregate(m15, 4)
    h4 = _aggregate(m15, 16)
    trades: list[BacktestTrade] = []

    for i in range(max(lookback, 30), len(m15) - 1):
        closed_m15 = m15[:i]
        current = closed_m15[-1]
        m15_closes = [c.close for c in closed_m15]
        m15_regime = _regime(m15_closes)

        # Only completed H1/H4 candles are exposed to the selector.
        completed_h1 = tuple(c for c in h1 if c.timestamp <= current.timestamp)
        completed_h4 = tuple(c for c in h4 if c.timestamp <= current.timestamp)
        context = StrategyContext(
            pair=pair,
            regime=m15_regime,
            bars={"M15": closed_m15, "H1": completed_h1, "H4": completed_h4},
            current_price=current.close,
            regimes={"M15": m15_regime, "H1": _regime([c.close for c in completed_h1]), "H4": _regime([c.close for c in completed_h4])},
        )
        selection = selector.evaluate(context)
        candidate = selection.selected
        if candidate is None or candidate.score < minimum_score:
            continue

        entry_bar = m15[i]
        entry = entry_bar.open
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

        outcome: float | None = None
        for future in m15[i:]:
            if candidate.direction == "BUY":
                hit_stop = future.low <= stop
                hit_target = future.high >= target
            else:
                hit_stop = future.high >= stop
                hit_target = future.low <= target

            # Conservative same-candle handling: if both are touched, count
            # the stop first because OHLC alone cannot establish tick order.
            if hit_stop:
                outcome = -1.0
                break
            if hit_target:
                outcome = reward_risk
                break
        if outcome is None:
            continue

        trades.append(BacktestTrade(
            pair=pair,
            timestamp=entry_bar.timestamp,
            strategy=candidate.strategy,
            direction=candidate.direction,
            score=candidate.score,
            entry=entry,
            stop_loss=stop,
            take_profit=target,
            outcome_r=outcome,
        ))

    return BacktestReport(pair=pair, trades=tuple(trades))
