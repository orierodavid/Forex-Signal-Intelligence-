from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from forex_intelligence.domain import Timeframe
from forex_intelligence.market_data.models import Bar, MarketSnapshot


class TwelveDataMarketDataProvider:
    """Quota-aware Twelve Data adapter with persistent cross-run caching.

    The scheduled GitHub Actions runner is ephemeral, so the cache directory is
    persisted by the workflow. H4/H1/M15 snapshots are refreshed only when their
    freshness windows expire. A hard daily request budget prevents accidental
    exhaustion of the Twelve Data Basic 800-credit daily allowance.
    """

    _INTERVALS = {
        Timeframe.H4: "4h",
        Timeframe.H1: "1h",
        Timeframe.M15: "15min",
    }
    _CACHE_TTL = {
        Timeframe.H4: timedelta(minutes=239),
        Timeframe.H1: timedelta(minutes=59),
        Timeframe.M15: timedelta(minutes=14),
    }
    # Keep 80 credits of headroom below the 800/day plan limit.
    DAILY_REQUEST_BUDGET = 720

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.twelvedata.com/time_series",
        cache_dir: str | Path = ".cache/twelvedata",
        daily_budget: int = DAILY_REQUEST_BUDGET,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Twelve Data API key is required")
        if daily_budget < 1 or daily_budget > 800:
            raise ValueError("daily_budget must be between 1 and 800")
        self.api_key = api_key
        self.base_url = base_url
        self.cache_dir = Path(cache_dir)
        self.cache_file = self.cache_dir / "snapshots.json"
        self.daily_budget = daily_budget
        self._state = self._load_state()

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

    @staticmethod
    def _iso(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat()

    def _load_state(self) -> dict[str, object]:
        if not self.cache_file.exists():
            return {"date": datetime.now(timezone.utc).date().isoformat(), "calls": 0, "snapshots": {}}
        try:
            state = json.loads(self.cache_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"date": datetime.now(timezone.utc).date().isoformat(), "calls": 0, "snapshots": {}}
        today = datetime.now(timezone.utc).date().isoformat()
        if state.get("date") != today:
            state = {"date": today, "calls": 0, "snapshots": state.get("snapshots", {})}
        state.setdefault("calls", 0)
        state.setdefault("snapshots", {})
        return state

    def _save_state(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        temp = self.cache_file.with_suffix(".tmp")
        temp.write_text(json.dumps(self._state, separators=(",", ":")), encoding="utf-8")
        temp.replace(self.cache_file)

    def _key(self, symbol: str, timeframe: Timeframe) -> str:
        return f"{self._symbol(symbol)}|{timeframe.value}"

    def _cached(self, symbol: str, timeframe: Timeframe) -> MarketSnapshot | None:
        raw = self._state.get("snapshots", {}).get(self._key(symbol, timeframe))
        if not isinstance(raw, dict):
            return None
        try:
            bars = tuple(
                Bar(
                    symbol=row["symbol"],
                    timeframe=Timeframe(row["timeframe"]),
                    timestamp=self._timestamp(row["timestamp"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    tick_volume=int(row.get("tick_volume", 0)),
                    spread_points=int(row.get("spread_points", 0)),
                    real_volume=int(row.get("real_volume", 0)),
                    quality="REAL",
                )
                for row in raw["bars"]
            )
            return MarketSnapshot(
                symbol=symbol,
                timeframe=timeframe,
                bars=bars,
                quality="REAL",
                provider="twelvedata-cache",
                retrieved_at=self._timestamp(raw["retrieved_at"]),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def _cache_is_fresh(self, snapshot: MarketSnapshot, timeframe: Timeframe, now: datetime) -> bool:
        return now - snapshot.retrieved_at < self._CACHE_TTL[timeframe]

    def _unavailable(self, symbol: str, timeframe: Timeframe, message: str) -> MarketSnapshot:
        return MarketSnapshot(
            symbol, timeframe, (), "UNAVAILABLE", "twelvedata", datetime.now(timezone.utc), message
        )

    def snapshot(self, symbol: str, timeframe: Timeframe, count: int = 300) -> MarketSnapshot:
        if count < 50:
            raise ValueError("At least 50 bars are required for regime analysis")
        if timeframe not in self._INTERVALS:
            raise ValueError(f"Unsupported cloud timeframe: {timeframe}")

        now = datetime.now(timezone.utc)
        cached = self._cached(symbol, timeframe)
        if cached is not None and self._cache_is_fresh(cached, timeframe, now):
            return cached

        calls = int(self._state.get("calls", 0))
        if calls >= self.daily_budget:
            if cached is not None:
                return cached
            return self._unavailable(symbol, timeframe, "Twelve Data daily request budget exhausted")

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
        retrieved = now
        try:
            with urlopen(request, timeout=20) as response:
                payload = json.load(response)
        except Exception as exc:
            # Count attempted API calls so transient failures cannot cause an
            # uncontrolled retry loop to exceed the daily allowance.
            self._state["calls"] = calls + 1
            self._save_state()
            return self._unavailable(symbol, timeframe, str(exc))

        self._state["calls"] = calls + 1
        if payload.get("status") == "error" or "values" not in payload:
            self._save_state()
            return self._unavailable(
                symbol,
                timeframe,
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
        snapshot = MarketSnapshot(symbol, timeframe, bars, "REAL", "twelvedata", retrieved)
        self._state["snapshots"][self._key(symbol, timeframe)] = {
            "retrieved_at": self._iso(retrieved),
            "bars": [
                {
                    **asdict(bar),
                    "timeframe": bar.timeframe.value,
                    "timestamp": self._iso(bar.timestamp),
                }
                for bar in bars
            ],
        }
        self._save_state()
        return snapshot

    @property
    def daily_calls_used(self) -> int:
        return int(self._state.get("calls", 0))

    @property
    def daily_calls_remaining(self) -> int:
        return max(0, self.daily_budget - self.daily_calls_used)
