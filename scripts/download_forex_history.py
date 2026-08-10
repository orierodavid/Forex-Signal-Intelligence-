from __future__ import annotations

import argparse
import csv
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

BASE_URL = "https://api.twelvedata.com/time_series"
PAIRS = ("EUR/USD", "USD/CHF", "AUD/USD", "USD/CAD", "NZD/USD")
INTERVALS = {"M15": "15min", "H1": "1h", "H4": "4h"}


def fetch(symbol: str, interval: str, start: str, end: str, api_key: str) -> list[dict[str, str]]:
    params = {
        "symbol": symbol,
        "interval": interval,
        "start_date": start,
        "end_date": end,
        "outputsize": 5000,
        "order": "asc",
        "timezone": "UTC",
        "apikey": api_key,
    }
    request = Request(f"{BASE_URL}?{urlencode(params)}", headers={"User-Agent": "Forex-Signal-Intelligence/1.0"})
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("status") != "ok":
        raise RuntimeError(f"Twelve Data error for {symbol} {interval}: {payload}")
    return payload.get("values", [])


def download_pair(symbol: str, interval_name: str, start: datetime, end: datetime, out: Path, api_key: str) -> int:
    interval = INTERVALS[interval_name]
    out.parent.mkdir(parents=True, exist_ok=True)
    rows: dict[str, dict[str, str]] = {}
    cursor = start
    # 5000 bars is the API response ceiling. 31 days is safely below that for
    # M15 and is also efficient for H1/H4. We advance from the last returned
    # timestamp to avoid duplicates at chunk boundaries.
    chunk_days = 31
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=chunk_days), end)
        values = fetch(symbol, interval, cursor.isoformat(), chunk_end.isoformat(), api_key)
        if not values:
            cursor = chunk_end
            continue
        for row in values:
            rows[row["datetime"]] = row
        last = datetime.fromisoformat(values[-1]["datetime"].replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        next_cursor = last + timedelta(seconds=1)
        if next_cursor <= cursor:
            cursor = chunk_end
        else:
            cursor = next_cursor
        time.sleep(0.15)

    ordered = [rows[key] for key in sorted(rows)]
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=("datetime", "open", "high", "low", "close", "volume"))
        writer.writeheader()
        writer.writerows(ordered)
    return len(ordered)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download M15/H1/H4 forex OHLC history from Twelve Data.")
    parser.add_argument("--start", required=True, help="UTC start, e.g. 2025-01-01T00:00:00+00:00")
    parser.add_argument("--end", required=True, help="UTC end, e.g. 2026-01-01T00:00:00+00:00")
    parser.add_argument("--data-dir", default="data/historical")
    parser.add_argument("--pairs", nargs="*", default=list(PAIRS))
    parser.add_argument("--api-key", default=os.getenv("TWELVE_DATA_API_KEY"))
    args = parser.parse_args()
    if not args.api_key:
        raise SystemExit("TWELVE_DATA_API_KEY is required; no API key was supplied.")

    start = datetime.fromisoformat(args.start.replace("Z", "+00:00"))
    end = datetime.fromisoformat(args.end.replace("Z", "+00:00"))
    if start.tzinfo is None or end.tzinfo is None:
        raise SystemExit("start/end must include a timezone; use UTC (+00:00).")
    safe_pairs = {pair: pair.replace("/", "_") for pair in PAIRS}
    for pair in args.pairs:
        if pair not in safe_pairs:
            raise SystemExit(f"Unsupported pair: {pair}")
        for timeframe in INTERVALS:
            path = Path(args.data_dir) / safe_pairs[pair] / f"{timeframe}.csv"
            count = download_pair(pair, timeframe, start, end, path, args.api_key)
            print(f"{pair} {timeframe}: {count} bars -> {path}")


if __name__ == "__main__":
    main()
