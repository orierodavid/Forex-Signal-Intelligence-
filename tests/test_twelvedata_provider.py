from datetime import datetime, timezone

from forex_intelligence.domain import Timeframe
from forex_intelligence.market_data.twelvedata import TwelveDataMarketDataProvider


def test_symbol_normalization():
    assert TwelveDataMarketDataProvider._symbol("EURUSD") == "EUR/USD"
    assert TwelveDataMarketDataProvider._symbol("eur/usd") == "EUR/USD"


def test_timestamp_is_utc():
    value = TwelveDataMarketDataProvider._timestamp("2026-08-09 08:00:00")
    assert value.tzinfo == timezone.utc
    assert value == datetime(2026, 8, 9, 8, 0, tzinfo=timezone.utc)


def test_supported_intervals():
    provider = TwelveDataMarketDataProvider("test-key")
    assert provider._INTERVALS[Timeframe.H4] == "4h"
    assert provider._INTERVALS[Timeframe.H1] == "1h"
    assert provider._INTERVALS[Timeframe.M15] == "15min"
