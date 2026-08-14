from __future__ import annotations

import os

from forex_intelligence.domain import Timeframe
from forex_intelligence.market_data.twelvedata import TwelveDataMarketDataProvider
from forex_intelligence.strategy_evidence import run_strategy_evidence

PAIRS = ("EURUSD", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD", "XAUUSD")


def main() -> None:
    api_key = os.environ.get("MARKET_DATA_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("MARKET_DATA_API_KEY is required")
    provider = TwelveDataMarketDataProvider(api_key=api_key, daily_budget=720)
    print("STRATEGY EVIDENCE MATRIX | M15 | H1/H4 context | no look-ahead")
    for pair in PAIRS:
        snapshot = provider.snapshot(pair, Timeframe.M15, count=5000)
        if not snapshot.available:
            print(f"{pair} | UNAVAILABLE | {snapshot.error}")
            continue
        rows = run_strategy_evidence(pair, snapshot.bars)
        positive = [r for r in rows if r.trades >= 30 and r.expectancy_r > 0 and r.profit_factor > 1.0]
        positive.sort(key=lambda r: (-r.expectancy_r, -r.trades))
        print(f"{pair} | rows={len(rows)} | positive_candidates={len(positive)}")
        for row in positive[:12]:
            print(
                f"{pair} | {row.strategy} | regime={row.regime} session={row.session} "
                f"vol={row.volatility_bucket} RR={row.reward_risk:g} trades={row.trades} "
                f"win={row.win_rate:.2f}% expR={row.expectancy_r:.3f} "
                f"PF={row.profit_factor:.2f} DD={row.max_drawdown_r:.2f}"
            )
    print(f"Twelve Data calls used: {provider.daily_calls_used}; remaining: {provider.daily_calls_remaining}")


if __name__ == "__main__":
    main()
