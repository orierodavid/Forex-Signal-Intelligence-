from __future__ import annotations

import os

from forex_intelligence.evidence_backtest import run_walk_forward
from forex_intelligence.domain import Timeframe
from forex_intelligence.market_data.twelvedata import TwelveDataMarketDataProvider

PAIRS = ("EURUSD", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD", "XAUUSD")


def main() -> None:
    api_key = os.environ.get("MARKET_DATA_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("MARKET_DATA_API_KEY is required")
    provider = TwelveDataMarketDataProvider(api_key=api_key, daily_budget=720)
    print("WALK-FORWARD EVIDENCE | M15 primary | H1/H4 confirmation")
    for pair in PAIRS:
        snapshot = provider.snapshot(pair, Timeframe.M15, count=5000)
        if not snapshot.available:
            print(f"{pair}: UNAVAILABLE: {snapshot.error}")
            continue
        current, adaptive = run_walk_forward(pair, snapshot.bars)
        print(
            f"{pair} | CURRENT trades={current.total_trades} win={current.win_rate:.2f}% "
            f"avgR={current.average_r:.3f} netR={current.net_r:.2f} PF={current.profit_factor:.2f} DD={current.max_drawdown_r:.2f} "
            f"risk_not_vetted={current.risk_not_vetted}"
        )
        print(
            f"{pair} | ADAPTIVE trades={adaptive.total_trades} win={adaptive.win_rate:.2f}% "
            f"avgR={adaptive.average_r:.3f} netR={adaptive.net_r:.2f} PF={adaptive.profit_factor:.2f} DD={adaptive.max_drawdown_r:.2f} "
            f"risk_not_vetted={adaptive.risk_not_vetted}"
        )
    print(f"Twelve Data calls used: {provider.daily_calls_used}; remaining: {provider.daily_calls_remaining}")


if __name__ == "__main__":
    main()
