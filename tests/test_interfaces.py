from forex_intelligence.providers import ExecutionBroker, MarketDataProvider, NewsProvider


def test_provider_interfaces_are_abstract() -> None:
    assert ExecutionBroker.__abstractmethods__
    assert MarketDataProvider.__abstractmethods__
    assert NewsProvider.__abstractmethods__
