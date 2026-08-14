from __future__ import annotations

import os
from dataclasses import dataclass
from statistics import mean
from typing import Sequence

from forex_intelligence.domain import Timeframe
from forex_intelligence.market_data.models import Bar
from forex_intelligence.market_data.twelvedata import TwelveDataMarketDataProvider
from forex_intelligence.strategy.strategies import DEFAULT_STRATEGIES
from forex_intelligence.strategy_evidence import _context, _levels, _outcome_r, _session, _volatility_bucket

PAIRS = ("EURUSD", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD", "XAUUSD")
RR_VALUES = (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)
MIN_TRAIN_TRADES = 30
TRAIN_BARS = 1000
TEST_BARS = 250
STEP_BARS = 250


@dataclass(frozen=True)
class ConditionalWalkForward:
    pair: str
    strategy: str
    regime: str
    session: str
    volatility: str
    reward_risk: float
    train_trades: int
    train_expectancy_r: float
    test_trades: int
    test_wins: int
    test_net_r: float
    test_expectancy_r: float
    test_profit_factor: float
    test_max_drawdown_r: float


def _trade_rows(pair: str, bars: Sequence[Bar], start: int, end: int):
    rows = []
    bars = tuple(bars)
    for i in range(max(50, start), min(end, len(bars) - 1)):
        context = _context(pair, bars, i)
        regime = context.regimes["M15"]
        session = _session(bars[i - 1].timestamp)
        volatility = _volatility_bucket(context.bars["M15"])
        for strategy in DEFAULT_STRATEGIES:
            result = strategy.evaluate(context)
            if not result.eligible or result.direction not in {"BUY", "SELL"} or result.score < 70:
                continue
            for rr in RR_VALUES:
                levels = _levels(bars, i, result.direction, rr)
                if levels is None:
                    continue
                outcome = _outcome_r(bars, i, result.direction, levels[0], levels[1], rr, 120)
                if outcome is None:
                    continue
                rows.append((result.strategy, regime, session, volatility, rr, outcome))
    return rows


def _stats(values: Sequence[float]):
    if not values:
        return 0, 0, 0.0, 0.0, 0.0
    wins = sum(v > 0 for v in values)
    net = sum(values)
    gp = sum(v for v in values if v > 0)
    gl = abs(sum(v for v in values if v < 0))
    equity = peak = dd = 0.0
    for v in values:
        equity += v
        peak = max(peak, equity)
        dd = max(dd, peak - equity)
    pf = gp / gl if gl else (float("inf") if gp else 0.0)
    return len(values), wins, net / len(values), pf, dd


def run_conditional_walk_forward(pair: str, bars: Sequence[Bar]) -> tuple[ConditionalWalkForward, ...]:
    bars = tuple(bars)
    reports = []
    if len(bars) < TRAIN_BARS + TEST_BARS:
        return ()

    for test_start in range(TRAIN_BARS, len(bars) - TEST_BARS + 1, STEP_BARS):
        train_start = max(0, test_start - TRAIN_BARS)
        test_end = min(len(bars), test_start + TEST_BARS)
        train = _trade_rows(pair, bars, train_start, test_start)
        test = _trade_rows(pair, bars, test_start, test_end)

        train_buckets = {}
        test_buckets = {}
        for row in train:
            key, outcome = row[:-1], row[-1]
            train_buckets.setdefault(key, []).append(outcome)
        for row in test:
            key, outcome = row[:-1], row[-1]
            test_buckets.setdefault(key, []).append(outcome)

        # A condition is promoted only from the preceding training window.
        for key, train_values in train_buckets.items():
            if len(train_values) < MIN_TRAIN_TRADES:
                continue
            train_exp = mean(train_values)
            if train_exp <= 0:
                continue
            test_values = test_buckets.get(key, [])
            if not test_values:
                continue
            trades, wins, test_exp, pf, dd = _stats(test_values)
            strategy, regime, session, volatility, rr = key
            reports.append(ConditionalWalkForward(
                pair=pair, strategy=strategy, regime=regime, session=session,
                volatility=volatility, reward_risk=rr, train_trades=len(train_values),
                train_expectancy_r=train_exp, test_trades=trades, test_wins=wins,
                test_net_r=sum(test_values), test_expectancy_r=test_exp,
                test_profit_factor=pf, test_max_drawdown_r=dd,
            ))
    return tuple(reports)


def main() -> None:
    api_key = os.environ.get("MARKET_DATA_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("MARKET_DATA_API_KEY is required")
    provider = TwelveDataMarketDataProvider(api_key=api_key, daily_budget=720)
    print("CONDITIONAL WALK-FORWARD EVIDENCE | M15 primary | H1/H4 confirmation | train-only promotion")
    for pair in PAIRS:
        snapshot = provider.snapshot(pair, Timeframe.M15, count=5000)
        if not snapshot.available:
            print(f"{pair} | UNAVAILABLE | {snapshot.error}")
            continue
        rows = run_conditional_walk_forward(pair, snapshot.bars)
        positive = [r for r in rows if r.test_trades >= 10 and r.test_expectancy_r > 0 and r.test_profit_factor > 1.0]
        positive.sort(key=lambda r: (-r.test_expectancy_r, -r.test_trades))
        print(f"{pair} | promoted_conditions={len(rows)} | positive_unseen_tests={len(positive)}")
        for r in positive[:12]:
            print(
                f"{pair} | {r.strategy} | regime={r.regime} session={r.session} vol={r.volatility} "
                f"RR={r.reward_risk:g} train={r.train_trades} trainExpR={r.train_expectancy_r:.3f} "
                f"test={r.test_trades} win={r.test_wins / r.test_trades * 100:.2f}% "
                f"testExpR={r.test_expectancy_r:.3f} PF={r.test_profit_factor:.2f} DD={r.test_max_drawdown_r:.2f}"
            )
    print(f"Twelve Data calls used: {provider.daily_calls_used}; remaining: {provider.daily_calls_remaining}")


if __name__ == "__main__":
    main()
