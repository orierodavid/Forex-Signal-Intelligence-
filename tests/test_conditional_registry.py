from forex_intelligence.strategy.conditional_registry import (
    ConditionalEvidence,
    ConditionalStrategyRegistry,
)


def evidence(**overrides):
    values = dict(
        pair="XAUUSD",
        strategy="BREAKOUT_RETEST",
        regime="TREND_UP",
        session="NEW_YORK",
        volatility="NORMAL",
        reward_risk=2.0,
        windows=4,
        positive_windows=3,
        median_test_expectancy_r=0.20,
        median_profit_factor=1.40,
        max_drawdown_r=8.0,
        promoted=True,
    )
    values.update(overrides)
    return ConditionalEvidence(**values)


def test_promotion_gate_requires_repeated_unseen_edge():
    assert evidence().qualifies()
    assert not evidence(windows=3).qualifies()
    assert not evidence(positive_windows=2).qualifies()
    assert not evidence(median_test_expectancy_r=0.10).qualifies()
    assert not evidence(median_profit_factor=1.15).qualifies()
    assert not evidence(max_drawdown_r=12.01).qualifies()


def test_registry_requires_explicit_promotion_even_when_statistics_qualify():
    registry = ConditionalStrategyRegistry((evidence(promoted=False),))
    assert registry.best("XAUUSD", "TREND_UP", "NEW_YORK", "NORMAL") is None


def test_registry_matches_exact_market_condition():
    candidate = evidence()
    registry = ConditionalStrategyRegistry((candidate,))
    assert registry.best("XAUUSD", "TREND_UP", "NEW_YORK", "NORMAL") == candidate
    assert registry.best("XAUUSD", "RANGE", "NEW_YORK", "NORMAL") is None
    assert registry.best("EURUSD", "TREND_UP", "NEW_YORK", "NORMAL") is None


def test_registry_prefers_best_forward_expectancy_then_pf():
    weaker = evidence(median_test_expectancy_r=0.20, median_profit_factor=2.0)
    stronger = evidence(median_test_expectancy_r=0.30, median_profit_factor=1.3)
    registry = ConditionalStrategyRegistry((weaker, stronger))
    assert registry.best("XAUUSD", "TREND_UP", "NEW_YORK", "NORMAL") == stronger
