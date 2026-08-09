from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from forex_intelligence.domain import Timeframe
from forex_intelligence.market_data.models import Bar, MarketSnapshot


class TwelveDataMarketDataProvider:
    """Cloud market-data adapter for scheduled, terminal-free analysis.

    This provider is read-only and has no broker/account access. It retrieves
    OHLC bars from Twelve Data so the scheduled signal cycle can run on a
    GitHub-hosted runner without a local MT5 terminal.
    """

    _INTERVALS = {
        Timeframe.H4: "4h",
        Timeframe.H1: "1h",
        Timeframe.M15: "15min",
    }

    def __init__(self, api_key: str, base_url: str = "https://api.twelvedata.com/time_series") -> None:
        if not api_key.strip():
            raise ValueError("Twelve Data API key is required")
        self.api_key = api_key
        self.base_url = base_url

    @staticmethod
    def _symbol(symbol: str) -> str:
        normalized = symbol.strip().upper()
        if "/" in normalized:
            return normalized
        if len(normalized) == 6:
            return f"{normalized[:3]}/{normalized[3:]}"
        return normalized

    @staticmethod
    def _timestamp(value: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def snapshot(self, symbol: str, timeframe: Timeframe, count: int = 300) -> MarketSnapshot:
        if count < 50:
            raise ValueError("At least 50 bars are required for regime analysis")
        if timeframe not in self._INTERVALS:
            raise ValueError(f"Unsupported cloud timeframe: {timeframe}")

        params = urlencode(
            {
                "symbol": self._symbol(symbol),
                "interval": self._INTERVALS[timeframe],
                "outputsize": count,
                "order": "ASC",
                "apikey": self.api_key,
            }
        )
        request = Request(
            f"{self.base_url}?{params}",
            headers={"User-Agent": "forex-signal-intelligence/0.1"},
        )
        retrieved = datetime.now(timezone.utc)
        try:
            with urlopen(request, timeout=20) as response:
                payload = json.load(response)
        except Exception as exc:
            return MarketSnapshot(
                symbol, timeframe, (), "UNAVAILABLE", "twelvedata", retrieved, str(exc)
            )

        if payload.get("status") == "error" or "values" not in payload:
            return MarketSnapshot(
                symbol,
                timeframe,
                (),
                "UNAVAILABLE",
                "twelvedata",
                retrieved,
                str(payload.get("message", "Twelve Data returned no values")),
            )

        bars = tuple(
            Bar(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=self._timestamp(row["datetime"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                quality="REAL",
            )
            for row in payload["values"]
        )
        return MarketSnapshot(symbol, timeframe, bars, "REAL", "twelvedata", retrieved)
