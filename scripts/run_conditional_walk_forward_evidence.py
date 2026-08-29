from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from statistics import mean, median
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
MIN_UNSEEN_WINDOWS = 4
MIN_POSITIVE_WINDOWS = 3
MIN_STABILITY = 0.75
MIN_MEDIAN_TEST_EXP_R = 0.10
MIN_MEDIAN_PF = 1.15
MAX_DD_R = 12.0
MIN_TEST_TRADES = 10
MIN_TOTAL_TEST_TRADES = 60
MIN_TOTAL_TEST_NET_R = 5.0
MAX_NEGATIVE_WINDOWS = 1


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
    window_start: int


@dataclass(frozen=True)
class ConditionalEvidenceSummary:
    pair: str
    strategy: str
    regime: str
    session: str
    volatility: str
    reward_risk: float
    windows: int
    positive_windows: int
    negative_windows: int
    stability: float
    median_test_expectancy_r: float
    median_test_profit_factor: float
    max_test_drawdown_r: float
    total_test_trades: int
    total_test_net_r: float
    promoted: bool


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

        for key, train_values in train_buckets.items():
            if len(train_values) < MIN_TRAIN_TRADES or mean(train_values) <= 0:
                continue
            test_values = test_buckets.get(key, [])
            if len(test_values) < MIN_TEST_TRADES:
                continue
            trades, wins, test_exp, pf, dd = _stats(test_values)
            strategy, regime, session, volatility, rr = key
            reports.append(ConditionalWalkForward(
                pair=pair, strategy=strategy, regime=regime, session=session,
                volatility=volatility, reward_risk=rr, train_trades=len(train_values),
                train_expectancy_r=mean(train_values), test_trades=trades, test_wins=wins,
                test_net_r=sum(test_values), test_expectancy_r=test_exp,
                test_profit_factor=pf, test_max_drawdown_r=dd, window_start=test_start,
            ))
    return tuple(reports)


def summarize_evidence(rows: Sequence[ConditionalWalkForward]) -> tuple[ConditionalEvidenceSummary, ...]:
    buckets = {}
    for row in rows:
        key = (row.pair, row.strategy, row.regime, row.session, row.volatility, row.reward_risk)
        buckets.setdefault(key, []).append(row)

    summaries = []
    for key, windows in buckets.items():
        positive = sum(r.test_expectancy_r > 0 and r.test_profit_factor > 1.0 for r in windows)
        negative = sum(r.test_expectancy_r <= 0 or r.test_profit_factor <= 1.0 for r in windows)
        stability = positive / len(windows) if windows else 0.0
        median_exp = median(r.test_expectancy_r for r in windows)
        median_pf = median(r.test_profit_factor for r in windows)
        total_trades = sum(r.test_trades for r in windows)
        total_net_r = sum(r.test_net_r for r in windows)
        max_dd = max(r.test_max_drawdown_r for r in windows)
        promoted = (
            len(windows) >= MIN_UNSEEN_WINDOWS
            and positive >= MIN_POSITIVE_WINDOWS
            and negative <= MAX_NEGATIVE_WINDOWS
            and stability >= MIN_STABILITY
            and median_exp > MIN_MEDIAN_TEST_EXP_R
            and median_pf > MIN_MEDIAN_PF
            and max_dd <= MAX_DD_R
            and total_trades >= MIN_TOTAL_TEST_TRADES
            and total_net_r >= MIN_TOTAL_TEST_NET_R
        )
        summaries.append(ConditionalEvidenceSummary(
            pair=key[0], strategy=key[1], regime=key[2], session=key[3],
            volatility=key[4], reward_risk=key[5], windows=len(windows),
            positive_windows=positive, negative_windows=negative, stability=stability,
            median_test_expectancy_r=median_exp, median_test_profit_factor=median_pf,
            max_test_drawdown_r=max_dd, total_test_trades=total_trades,
            total_test_net_r=total_net_r, promoted=promoted,
        ))
    return tuple(sorted(summaries, key=lambda r: (-r.median_test_expectancy_r, -r.total_test_trades)))


def build_strategy_profile(summaries: Sequence[ConditionalEvidenceSummary]) -> dict:
    """Reduce promoted conditional evidence to one robust strategy per pair/regime.

    Session/volatility/RR are research dimensions. Live selection uses pair+regime,
    so an assignment is emitted only when promoted evidence exists across at least
    two distinct research conditions and the aggregate OOS edge remains positive.
    """
    groups: dict[tuple[str, str, str], list[ConditionalEvidenceSummary]] = {}
    for row in summaries:
        if row.promoted:
            groups.setdefault((row.pair, row.regime, row.strategy), []).append(row)

    candidates = []
    for (pair, regime, strategy), rows in groups.items():
        conditions = {(r.session, r.volatility, r.reward_risk) for r in rows}
        trades = sum(r.total_test_trades for r in rows)
        weighted_exp = sum(r.median_test_expectancy_r * r.total_test_trades for r in rows) / max(trades, 1)
        median_pf = median(r.median_test_profit_factor for r in rows)
        stability = min(r.stability for r in rows)
        if len(conditions) < 2 or trades < MIN_TOTAL_TEST_TRADES or weighted_exp <= MIN_MEDIAN_TEST_EXP_R or median_pf <= MIN_MEDIAN_PF:
            continue
        candidates.append((pair, regime, strategy, weighted_exp, median_pf, stability, trades))

    assignments: dict[str, str] = {}
    for pair, regime in sorted({(c[0], c[1]) for c in candidates}):
        options = [c for c in candidates if c[0] == pair and c[1] == regime]
        winner = max(options, key=lambda c: (c[3], c[4], c[5], c[6], c[2]))
        assignments[f"{pair}|{regime}"] = winner[2]

    return {
        "version": 1,
        "generated_from": "conditional_walk_forward",
        "min_trades": MIN_TOTAL_TEST_TRADES,
        "min_expectancy_r": MIN_MEDIAN_TEST_EXP_R,
        "min_profit_factor": MIN_MEDIAN_PF,
        "assignments": assignments,
    }


def main() -> None:
    api_key = os.environ.get("MARKET_DATA_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("MARKET_DATA_API_KEY is required")
    provider = TwelveDataMarketDataProvider(api_key=api_key, daily_budget=720)
    all_summaries = []
    print("CONDITIONAL WALK-FORWARD EVIDENCE | M15 primary | H1/H4 confirmation | train-only promotion")
    for pair in PAIRS:
        snapshot = provider.snapshot(pair, Timeframe.M15, count=5000)
        if not snapshot.available:
            print(f"{pair} | UNAVAILABLE | {snapshot.error}")
            continue
        rows = run_conditional_walk_forward(pair, snapshot.bars)
        summaries = summarize_evidence(rows)
        all_summaries.extend(summaries)
        promoted = [r for r in summaries if r.promoted]
        positive = [r for r in summaries if r.positive_windows >= 1 and r.median_test_expectancy_r > 0 and r.median_test_profit_factor > 1.0]
        print(f"{pair} | windows={len({r.window_start for r in rows})} | conditions={len(summaries)} | promoted={len(promoted)} | positive={len(positive)}")
        for r in promoted[:12]:
            print(
                f"{pair} | PROMOTE | {r.strategy} | regime={r.regime} session={r.session} vol={r.volatility} "
                f"RR={r.reward_risk:g} windows={r.windows} positive={r.positive_windows} stability={r.stability:.2f} "
                f"medianExpR={r.median_test_expectancy_r:.3f} medianPF={r.median_test_profit_factor:.2f} "
                f"maxDD={r.max_test_drawdown_r:.2f} trades={r.total_test_trades} netR={r.total_test_net_r:.2f}"
            )
    registry = [asdict(r) for r in all_summaries]
    with open("conditional_walk_forward_registry.json", "w", encoding="utf-8") as fh:
        json.dump(registry, fh, indent=2, sort_keys=True)
    profile = build_strategy_profile(all_summaries)
    with open("strategy_profile.json", "w", encoding="utf-8") as fh:
        json.dump(profile, fh, indent=2, sort_keys=True)
    print(f"Registry written: conditional_walk_forward_registry.json | promoted={sum(r.promoted for r in all_summaries)}")
    print(f"Strategy profile written: strategy_profile.json | assignments={len(profile['assignments'])}")
    print(f"Twelve Data calls used: {provider.daily_calls_used}; remaining: {provider.daily_calls_remaining}")


if __name__ == "__main__":
    main()
