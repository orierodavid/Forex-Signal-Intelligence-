from __future__ import annotations

import json
import os
from pathlib import Path

from forex_intelligence.evidence_backtest import EvidenceReport, run_walk_forward
from forex_intelligence.domain import Timeframe
from forex_intelligence.market_data.twelvedata import TwelveDataMarketDataProvider

PAIRS = ("EURUSD", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD", "XAUUSD")
PROFILE_PATH = Path(os.getenv("STRATEGY_PROFILE_PATH", "strategy_profile.json"))
MIN_TRADES = 30
MIN_EXPECTANCY_R = 0.0
MIN_PROFIT_FACTOR = 1.05


def _promote(report: EvidenceReport, pair: str, assignments: dict[str, str], evidence: dict[str, dict]) -> None:
    for regime, regime_report in report.by_regime().items():
        eligible = []
        for strategy, strategy_report in regime_report.by_strategy().items():
            if (strategy_report.total_trades >= MIN_TRADES
                    and strategy_report.average_r > MIN_EXPECTANCY_R
                    and strategy_report.profit_factor >= MIN_PROFIT_FACTOR):
                eligible.append((strategy, strategy_report))
        if not eligible:
            continue
        eligible.sort(key=lambda x: (x[1].average_r, x[1].profit_factor, x[1].total_trades), reverse=True)
        strategy, selected = eligible[0]
        key = f"{pair}|{regime}".upper()
        assignments[key] = strategy
        evidence[key] = {
            "strategy": strategy,
            "trades": selected.total_trades,
            "expectancy_r": round(selected.average_r, 6),
            "profit_factor": round(selected.profit_factor, 6),
            "win_rate": round(selected.win_rate, 4),
            "selector": report.selector,
        }


def _publish(assignments: dict[str, str], evidence: dict[str, dict]) -> None:
    PROFILE_PATH.write_text(json.dumps({
        "version": 2,
        "source": "out_of_sample_conditional_walk_forward",
        "min_trades": MIN_TRADES,
        "min_expectancy_r": MIN_EXPECTANCY_R,
        "min_profit_factor": MIN_PROFIT_FACTOR,
        "assignments": dict(sorted(assignments.items())),
        "evidence": dict(sorted(evidence.items())),
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"PUBLISHED_PROFILE: {PROFILE_PATH} assignments={len(assignments)}")
    for key, strategy in sorted(assignments.items()):
        print(f"PROFILE: {key} -> {strategy}")
    if not assignments:
        print("PROFILE: EMPTY — no pair/regime met promotion criteria")


def main() -> None:
    api_key = os.environ.get("MARKET_DATA_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("MARKET_DATA_API_KEY is required")
    provider = TwelveDataMarketDataProvider(api_key=api_key, daily_budget=720)
    assignments: dict[str, str] = {}
    evidence: dict[str, dict] = {}
    print("WALK-FORWARD EVIDENCE | M15 primary | H1/H4 confirmation | OOS profile promotion")
    for pair in PAIRS:
        snapshot = provider.snapshot(pair, Timeframe.M15, count=5000)
        if not snapshot.available:
            print(f"{pair}: UNAVAILABLE: {snapshot.error}")
            continue
        current, adaptive = run_walk_forward(pair, snapshot.bars)
        print(f"{pair} | CURRENT trades={current.total_trades} win={current.win_rate:.2f}% avgR={current.average_r:.3f} netR={current.net_r:.2f} PF={current.profit_factor:.2f} DD={current.max_drawdown_r:.2f} risk_not_vetted={current.risk_not_vetted}")
        print(f"{pair} | ADAPTIVE trades={adaptive.total_trades} win={adaptive.win_rate:.2f}% avgR={adaptive.average_r:.3f} netR={adaptive.net_r:.2f} PF={adaptive.profit_factor:.2f} DD={adaptive.max_drawdown_r:.2f} risk_not_vetted={adaptive.risk_not_vetted}")
        _promote(adaptive, pair, assignments, evidence)
    _publish(assignments, evidence)
    print(f"Twelve Data calls used: {provider.daily_calls_used}; remaining: {provider.daily_calls_remaining}")


if __name__ == "__main__":
    main()
