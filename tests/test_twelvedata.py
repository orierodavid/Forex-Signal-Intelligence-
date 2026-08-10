import json
from datetime import datetime, timedelta, timezone

from forex_intelligence.domain import Timeframe
from forex_intelligence.market_data.twelvedata import TwelveDataMarketDataProvider


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        return iter(())

    def read(self):
        return json.dumps(self.payload).encode()


def payload():
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    return {
        "status": "ok",
        "values": [
            {
                "datetime": (now - timedelta(minutes=15)).isoformat(),
                "open": "100",
                "high": "101",
                "low": "99",
                "close": "100.5",
            },
            {
                "datetime": now.isoformat(),
                "open": "100.5",
                "high": "102",
                "low": "100",
                "close": "101",
            },
        ],
    }


def test_twelve_data_provider_reuses_fresh_cache(tmp_path, monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        return FakeResponse(payload())

    monkeypatch.setattr(
        "forex_intelligence.market_data.twelvedata.urlopen", fake_urlopen
    )
    provider = TwelveDataMarketDataProvider("key", cache_dir=tmp_path)
    first = provider.snapshot("EURUSD", Timeframe.M15, count=50)
    second = provider.snapshot("EURUSD", Timeframe.M15, count=50)

    assert first.available
    assert second.available
    assert len(calls) == 1
    assert provider.daily_calls_used == 1


def test_twelve_data_provider_persists_cache_across_instances(tmp_path, monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        return FakeResponse(payload())

    monkeypatch.setattr(
        "forex_intelligence.market_data.twelvedata.urlopen", fake_urlopen
    )
    first = TwelveDataMarketDataProvider("key", cache_dir=tmp_path)
    first.snapshot("XAUUSD", Timeframe.H1, count=50)
    second = TwelveDataMarketDataProvider("key", cache_dir=tmp_path)
    second.snapshot("XAUUSD", Timeframe.H1, count=50)

    assert len(calls) == 1
    assert second.daily_calls_used == 1


def test_twelve_data_provider_hard_budget(tmp_path, monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        return FakeResponse(payload())

    monkeypatch.setattr(
        "forex_intelligence.market_data.twelvedata.urlopen", fake_urlopen
    )
    provider = TwelveDataMarketDataProvider("key", cache_dir=tmp_path, daily_budget=1)
    provider.snapshot("EURUSD", Timeframe.M15, count=50)
    unavailable = provider.snapshot("GBPUSD", Timeframe.M15, count=50)

    assert len(calls) == 1
    assert provider.daily_calls_used == 1
    assert provider.daily_calls_remaining == 0
    assert unavailable.available is False
