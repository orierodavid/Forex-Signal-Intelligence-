from datetime import datetime, timezone

import pytest

from forex_intelligence.domain import Timeframe
from forex_intelligence.market_data import MT5MarketDataProvider


class FakeMT5:
    TIMEFRAME_H1 = 16385

    def __init__(self, rates=None, error=(0, "")):
        self.rates = rates
        self.error = error
        self.initialized = False
        self.shutdown_called = False

    def initialize(self, **kwargs):
        self.initialized = True
        return True

    def shutdown(self):
        self.shutdown_called = True

    def last_error(self):
        return self.error

    def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
        return self.rates


def rate(ts: int, close: float) -> dict[str, int | float]:
    return {"time": ts, "open": close - .001, "high": close + .001, "low": close - .002, "close": close, "tick_volume": 10, "spread": 2, "real_volume": 0}


def test_mt5_adapter_normalizes_bars() -> None:
    fake = FakeMT5([rate(2, 1.2), rate(1, 1.1)])
    provider = MT5MarketDataProvider(mt5_module=fake)
    provider.connect()
    snapshot = provider.snapshot("EURUSD", Timeframe.H1, count=50)
    assert snapshot.available
    assert [bar.close for bar in snapshot.bars] == [1.1, 1.2]
    provider.shutdown()
    assert fake.shutdown_called


def test_mt5_adapter_reports_provider_failure() -> None:
    fake = FakeMT5(None, error=(500, "terminal unavailable"))
    snapshot = MT5MarketDataProvider(mt5_module=fake).snapshot("EURUSD", Timeframe.H1, count=50)
    assert snapshot.available is False
    assert snapshot.quality == "UNAVAILABLE"
    assert "terminal unavailable" in snapshot.error


def test_mt5_adapter_requires_reasonable_history() -> None:
    with pytest.raises(ValueError):
        MT5MarketDataProvider(mt5_module=FakeMT5([])).snapshot("EURUSD", Timeframe.H1, count=10)
