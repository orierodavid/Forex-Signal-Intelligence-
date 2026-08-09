from __future__ import annotations

from forex_intelligence.strategy import StrategyContext, StrategySelector
from forex_intelligence.strategy.base import StrategyResult
from forex_intelligence.strategy.strategies import (
    BreakoutRetestStrategy,
    LiquiditySweepReversalStrategy,
    MeanReversionStrategy,
    MomentumContinuationStrategy,
    RangeBreakoutStrategy,
    SupportResistanceRejectionStrategy,
    TrendPullbackStrategy,
)


def bar(open_: float, high: float, low: float, close: float) -> dict[str, float]:
    return {"open": open_, "high": high, "low": low, "close": close}


def rising_bars(n: int = 30, start: float = 1.10) -> list[dict[str, float]]:
    return [bar(start + i * 0.001, start + i * 0.0015, start + i * 0.0008, start + (i + 1) * 0.001) for i in range(n)]


def test_all_seven_strategy_families_are_present() -> None:
    strategies = (
        TrendPullbackStrategy(),
        BreakoutRetestStrategy(),
        LiquiditySweepReversalStrategy(),
        RangeBreakoutStrategy(),
        SupportResistanceRejectionStrategy(),
        MomentumContinuationStrategy(),
        MeanReversionStrategy(),
    )
    assert len(strategies) == 7
    assert len({strategy.name for strategy in strategies}) == 7


def test_result_contract_rejects_invalid_direction() -> None:
    try:
        StrategyResult("X", "HOLD", 50, True, "t", "i")
    except ValueError:
        return
    raise AssertionError("invalid direction was accepted")


def test_selector_returns_no_trade_when_regime_is_incompatible() -> None:
    context = StrategyContext("EURUSD", "UNTRADEABLE", {"M15": rising_bars()}, 1.13)
    selection = StrategySelector().evaluate(context)
    assert selection.selected is None
    assert selection.direction == "NO_TRADE"


def test_breakout_retest_can_select_a_clean_breakout() -> None:
    bars = [bar(1.10, 1.102, 1.098, 1.10) for _ in range(24)]
    bars.append(bar(1.10, 1.106, 1.101, 1.105))
    context = StrategyContext("EURUSD", "TREND_UP", {"M15": bars}, 1.105)
    result = BreakoutRetestStrategy().evaluate(context)
    assert result.eligible
    assert result.direction == "BUY"
    assert result.score >= 80


def test_momentum_requires_directional_persistence() -> None:
    bars = [bar(1.10 + i * 0.001, 1.102 + i * 0.001, 1.099 + i * 0.001, 1.101 + i * 0.001) for i in range(8)]
    context = StrategyContext("EURUSD", "STRONG_TREND_UP", {"M15": bars}, 1.109)
    result = MomentumContinuationStrategy().evaluate(context)
    assert result.eligible
    assert result.direction == "BUY"
