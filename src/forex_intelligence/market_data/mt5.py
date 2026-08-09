from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from forex_intelligence.domain import Timeframe
from forex_intelligence.market_data.models import MarketSnapshot


class MT5MarketDataProvider:
    """Read-only MT5 market-data adapter.

    This adapter never submits orders. The MetaTrader5 package is optional so
    analysis and CI can run without a locally installed MT5 terminal.
    """

    _TIMEFRAMES = {"H4": "TIMEFRAME_H4", "H1": "TIMEFRAME_H1", "M15": "TIMEFRAME_M15", "M5": "TIMEFRAME_M5"}

    def __init__(self, terminal_path: str | None = None, mt5_module: Any | None = None) -> None:
        self.terminal_path = terminal_path
        self._mt5 = mt5_module

    def _module(self) -> Any:
        if self._mt5 is None:
            try:
                import MetaTrader5 as mt5
            except ImportError as exc:
                raise RuntimeError("MetaTrader5 package is not installed") from exc
            self._mt5 = mt5
        return self._mt5

    def connect(self) -> None:
        mt5 = self._module()
        kwargs = {}
        if self.terminal_path:
            kwargs["path"] = self.terminal_path
        if not mt5.initialize(**kwargs):
            raise ConnectionError(f"MT5 initialize failed: {mt5.last_error()}")

    def shutdown(self) -> None:
        if self._mt5 is not None:
            self._mt5.shutdown()

    def snapshot(self, symbol: str, timeframe: Timeframe, count: int = 300) -> MarketSnapshot:
        if count < 50:
            raise ValueError("At least 50 bars are required for regime analysis")
        mt5 = self._module()
        tf_name = self._TIMEFRAMES[timeframe.value]
        tf = getattr(mt5, tf_name)
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        retrieved = datetime.now(timezone.utc)
        if rates is None:
            return MarketSnapshot(symbol, timeframe, (), "UNAVAILABLE", "mt5", retrieved, str(mt5.last_error()))

        bars = tuple(
            __import__("forex_intelligence.market_data.models", fromlist=["Bar"]).Bar(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=datetime.fromtimestamp(int(row["time"]), tz=timezone.utc),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                tick_volume=int(row["tick_volume"]),
                spread_points=int(row["spread"]),
                real_volume=int(row["real_volume"]),
                quality="REAL",
            )
            for row in rates
        )
        # MT5 returns bars from present to past for position-based requests;
        # normalize to chronological order for indicator calculations.
        bars = tuple(sorted(bars, key=lambda bar: bar.timestamp))
        return MarketSnapshot(symbol, timeframe, bars, "REAL", "mt5", retrieved)
