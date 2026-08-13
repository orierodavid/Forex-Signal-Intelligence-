from forex_intelligence.adaptive_selector import (
    AdaptiveCandidate,
    AdaptiveStrategySelector,
    Direction,
    HistoricalEdge,
    MarketState,
    Regime,
)


def candidate(strategy, direction, score, setup=85, entry=85, rr=85, edge=None):
    return AdaptiveCandidate(
        strategy=strategy,
        direction=direction,
        base_score=score,
        setup_quality=setup,
        entry_quality=entry,
        risk_reward_quality=rr,
        historical_edge=edge,
    )


def test_trend_regime_only_allows_compatible_strategies():
    selector = AdaptiveStrategySelector()
    state = MarketState(
        pair="EURUSD",
        regime=Regime.TREND_UP,
        h1_regime=Regime.TREND_UP,
        h4_regime=Regime.TREND_UP,
    )
    result = selector.evaluate(
        state,
        [
            candidate("MEAN_REVERSION", Direction.BUY, 99),
            candidate("TREND_PULLBACK", Direction.BUY, 78),
        ],
    )
    assert result.selected is not None
    assert result.selected.strategy == "TREND_PULLBACK"


def test_m15_direction_is_a_gate_against_opposing_strategy():
    selector = AdaptiveStrategySelector()
    state = MarketState(
        pair="EURUSD",
        regime=Regime.TREND_UP,
        h1_regime=Regime.TREND_UP,
        h4_regime=Regime.TREND_UP,
    )
    result = selector.evaluate(
        state,
        [
            candidate("MOMENTUM_CONTINUATION", Direction.SELL, 99),
            candidate("TREND_PULLBACK", Direction.BUY, 78),
        ],
    )
    assert result.selected is not None
    assert result.selected.direction is Direction.BUY


def test_close_opposing_candidates_produce_no_trade():
    selector = AdaptiveStrategySelector()
    state = MarketState(pair="EURUSD", regime=Regime.TRANSITION)
    result = selector.evaluate(
        state,
        [
            candidate("BREAKOUT_RETEST", Direction.BUY, 80),
            candidate("LIQUIDITY_SWEEP_REVERSAL", Direction.SELL, 79),
        ],
    )
    assert result.selected is None
    assert result.status == "NO_TRADE"


def test_historical_edge_can_break_ties_without_overriding_current_gates():
    selector = AdaptiveStrategySelector()
    state = MarketState(pair="EURUSD", regime=Regime.TREND_UP)
    result = selector.evaluate(
        state,
        [
            candidate(
                "TREND_PULLBACK",
                Direction.BUY,
                78,
                edge=HistoricalEdge(samples=200, expectancy_r=0.45, win_rate=0.68, profit_factor=1.7),
            ),
            candidate(
                "MOMENTUM_CONTINUATION",
                Direction.BUY,
                80,
                edge=HistoricalEdge(samples=200, expectancy_r=0.05, win_rate=0.52, profit_factor=1.1),
            ),
        ],
    )
    assert result.selected is not None
    assert result.selected.strategy == "TREND_PULLBACK"


def test_70_to_74_is_risk_not_vetted_and_75_is_qualified():
    selector = AdaptiveStrategySelector()
    state = MarketState(pair="EURUSD", regime=Regime.TREND_UP)
    low = selector.evaluate(state, [candidate("TREND_PULLBACK", Direction.BUY, 70)])
    high = selector.evaluate(state, [candidate("TREND_PULLBACK", Direction.BUY, 75)])
    assert low.status == "RISK_NOT_VETTED"
    assert high.status == "QUALIFIED"
