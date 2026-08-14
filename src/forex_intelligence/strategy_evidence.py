from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import mean
from typing import Sequence

from forex_intelligence.market_data.models import Bar
from forex_intelligence.strategy.base import StrategyContext
from forex_intelligence.strategy.strategies import DEFAULT_STRATEGIES


@dataclass(frozen=True)
class StrategyEvidence:
    pair: str
    strategy: str
    regime: str
    session: str
    volatility_bucket: str
    reward_risk: float
    trades: int
    wins: int
    net_r: float
    expectancy_r: float
    profit_factor: float
    max_drawdown_r: float

    @property
    def win_rate(self) -> float:
        return self.wins / self.trades * 100.0 if self.trades else 0.0


def _regime(closes: Sequence[float]) -> str:
    if len(closes) < 20:
        return "TRANSITION"
    a = mean(closes[-20:-10])
    b = mean(closes[-10:])
    change = (b - a) / max(abs(a), 1e-12)
    if change > 0.0015:
        return "TREND_UP"
    if change < -0.0015:
        return "TREND_DOWN"
    return "RANGE"


def _aggregate(bars: Sequence[Bar], size: int) -> tuple[Bar, ...]:
    result: list[Bar] = []
    for i in range(0, len(bars), size):
        chunk = bars[i:i + size]
        if len(chunk) < size:
            break
        result.append(Bar(symbol=chunk[-1].symbol, timeframe=chunk[-1].timeframe,
                          timestamp=chunk[-1].timestamp, open=chunk[0].open,
                          high=max(x.high for x in chunk), low=min(x.low for x in chunk),
                          close=chunk[-1].close, quality="REAL"))
    return tuple(result)


def _context(pair: str, bars: Sequence[Bar], i: int) -> StrategyContext:
    closed = tuple(bars[:i])
    h1, h4 = _aggregate(closed, 4), _aggregate(closed, 16)
    regimes = {
        "M15": _regime([b.close for b in closed]),
        "H1": _regime([b.close for b in h1]),
        "H4": _regime([b.close for b in h4]),
    }
    return StrategyContext(pair=pair, regime=regimes["M15"],
                           bars={"M15": closed, "H1": h1, "H4": h4},
                           current_price=closed[-1].close, regimes=regimes)


def _session(timestamp: datetime) -> str:
    """Classify a UTC-aware bar timestamp into the evidence session."""
    if not isinstance(timestamp, datetime):
        raise TypeError(f"bar timestamp must be datetime, got {type(timestamp).__name__}")
    hour = timestamp.hour
    if 7 <= hour < 12:
        return "LONDON"
    if 12 <= hour < 17:
        return "NEW_YORK"
    if 17 <= hour < 21:
        return "LONDON_NY_OVERLAP"
    return "ASIA_OTHER"


def _atr(bars: Sequence[Bar], period: int = 14) -> float:
    if len(bars) < period:
        return 0.0
    return mean(b.high - b.low for b in bars[-period:])


def _volatility_bucket(bars: Sequence[Bar]) -> str:
    if len(bars) < 42:
        return "UNKNOWN"
    fast = _atr(bars, 14)
    slow = _atr(bars[-42:-14], 14)
    if slow <= 0:
        return "UNKNOWN"
    ratio = fast / slow
    if ratio >= 1.35:
        return "HIGH"
    if ratio <= 0.75:
        return "LOW"
    return "NORMAL"


def _levels(bars: Sequence[Bar], i: int, direction: str, rr: float) -> tuple[float, float] | None:
    recent = bars[i - 10:i]
    if len(recent) < 10:
        return None
    entry = bars[i - 1].close
    if direction == "BUY":
        stop = min(b.low for b in recent)
        risk = entry - stop
        return (stop, entry + risk * rr) if risk > 0 else None
    if direction == "SELL":
        stop = max(b.high for b in recent)
        risk = stop - entry
        return (stop, entry - risk * rr) if risk > 0 else None
    return None


def _outcome_r(bars: Sequence[Bar], start: int, direction: str, stop: float, target: float, rr: float, lookahead: int) -> float | None:
    for bar in bars[start:start + lookahead]:
        if direction == "BUY":
            hit_stop, hit_target = bar.low <= stop, bar.high >= target
        else:
            hit_stop, hit_target = bar.high >= stop, bar.low <= target
        if hit_stop:
            return -1.0
        if hit_target:
            return rr
    return None


def run_strategy_evidence(
    pair: str,
    m15_bars: Sequence[Bar],
    *,
    reward_risks: Sequence[float] = (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0),
    lookahead_bars: int = 120,
) -> tuple[StrategyEvidence, ...]:
    """Evaluate every strategy independently without future-data leakage.

    Each decision uses only bars before index i. Results are bucketed by pair,
    M15 regime, UTC session, volatility regime and reward/risk target.
    """
    bars = tuple(m15_bars)
    buckets: dict[tuple[str, str, str, str, float], list[float]] = {}
    for i in range(50, len(bars) - 1):
        context = _context(pair, bars, i)
        regime = context.regimes["M15"]
        session = _session(bars[i - 1].timestamp)
        volatility = _volatility_bucket(context.bars["M15"])
        for strategy in DEFAULT_STRATEGIES:
            result = strategy.evaluate(context)
            if not result.eligible or result.direction not in {"BUY", "SELL"} or result.score < 70:
                continue
            for rr in reward_risks:
                levels = _levels(bars, i, result.direction, rr)
                if levels is None:
                    continue
                outcome = _outcome_r(bars, i, result.direction, levels[0], levels[1], rr, lookahead_bars)
                if outcome is None:
                    continue
                key = (result.strategy, regime, session, volatility, rr)
                buckets.setdefault(key, []).append(outcome)

    reports: list[StrategyEvidence] = []
    for (strategy, regime, session, volatility, rr), values in sorted(buckets.items()):
        wins = sum(v > 0 for v in values)
        net = sum(values)
        gross_profit = sum(v for v in values if v > 0)
        gross_loss = abs(sum(v for v in values if v < 0))
        equity = peak = dd = 0.0
        for value in values:
            equity += value
            peak = max(peak, equity)
            dd = max(dd, peak - equity)
        reports.append(StrategyEvidence(
            pair=pair, strategy=strategy, regime=regime, session=session,
            volatility_bucket=volatility, reward_risk=rr, trades=len(values),
            wins=wins, net_r=net, expectancy_r=net / len(values),
            profit_factor=gross_profit / gross_loss if gross_loss else (float("inf") if gross_profit else 0.0),
            max_drawdown_r=dd,
        ))
    return tuple(reports)
