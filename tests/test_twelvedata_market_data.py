from __future__ import annotations

import json
from datetime import timezone

from forex_intelligence.domain import Timeframe
from forex_intelligence.market_data.twelvedata import TwelveDataMarketDataProvider


def test_twelve_data_provider_normalizes_forex_symbol_and_builds_real_snapshot(monkeypatch):
    payload = {
        "values": [
            {
                "datetime": "2026-08-09 09:00:00",
                "open": "1.1000",
                "high": "1.1020",
                "low": "1.0990",
                "close": "1.1010",
            }
        ]
        * 50
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(payload).encode()

    monkeypatch.setattr(
        "forex_intelligence.market_data.twelvedata.urlopen",
        lambda request, timeout=20: FakeResponse(),
    )

    provider = TwelveDataMarketDataProvider("test-key")
    snapshot = provider.snapshot("EURUSD", Timeframe.H1, count=50)

    assert snapshot.available
    assert snapshot.quality == "REAL"
    assert snapshot.provider == "twelvedata"
    assert len(snapshot.bars) == 50
    assert snapshot.bars[0].timestamp.tzinfo == timezone.utc
    assert snapshot.bars[-1].close == 1.101


def test_twelve_data_provider_marks_api_errors_unavailable(monkeypatch):
    payload = {"status": "error", "message": "invalid api key"}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(payload).encode()

    monkeypatch.setattr(
        "forex_intelligence.market_data.twelvedata.urlopen",
        lambda request, timeout=20: FakeResponse(),
    )

    snapshot = TwelveDataMarketDataProvider("bad-key").snapshot("EUR/USD", Timeframe.M15, 50)

    assert not snapshot.available
    assert snapshot.quality == "UNAVAILABLE"
    assert "invalid api key" in (snapshot.error or "")
