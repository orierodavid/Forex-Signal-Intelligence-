from __future__ import annotations

import argparse
import csv
from pathlib import Path

from forex_intelligence.backtest import Candle, run_backtest


def load_csv(path: Path) -> list[Candle]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        required = {"timestamp", "open", "high", "low", "close"}
        if not required.issubset(rows.fieldnames or set()):
            raise ValueError(f"CSV must contain: {', '.join(sorted(required))}")
        return [
            Candle(
                timestamp=row["timestamp"],
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
            )
            for row in rows
        ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay the M15/H1/H4 Forex strategy selector")
    parser.add_argument("csv", type=Path, help="M15 OHLC CSV")
    parser.add_argument("--pair", required=True)
    parser.add_argument("--lookback", type=int, default=120)
    parser.add_argument("--minimum-score", type=float, default=70.0)
    args = parser.parse_args()

    report = run_backtest(
        args.pair,
        load_csv(args.csv),
        minimum_score=args.minimum_score,
        lookback=args.lookback,
    )
    print(f"Pair: {report.pair}")
    print(f"Trades: {report.total_trades}")
    print(f"Wins: {report.wins}")
    print(f"Losses: {report.losses}")
    print(f"Win rate: {report.win_rate:.2f}%")
    print(f"Net R: {report.net_r:.2f}")
    print(f"Profit factor: {report.profit_factor:.2f}")
    print(f"Risk-not-vetted trades: {report.risk_not_vetted_trades}")

    for trade in report.trades:
        print(
            f"{trade.timestamp} {trade.direction} {trade.strategy} "
            f"score={trade.score:.0f} status={trade.risk_status} "
            f"entry={trade.entry:.8f} sl={trade.stop_loss:.8f} "
            f"tp={trade.take_profit:.8f} outcome={trade.outcome_r:+.2f}R"
        )


if __name__ == "__main__":
    main()
