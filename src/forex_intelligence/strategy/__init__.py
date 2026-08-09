"""Modular strategy framework for regime-aware setup detection."""

from .base import Strategy, StrategyContext, StrategyResult
from .selector import StrategySelector
from .strategies import (
    BreakoutRetestStrategy,
    LiquiditySweepReversalStrategy,
    MeanReversionStrategy,
    MomentumContinuationStrategy,
    RangeBreakoutStrategy,
    SupportResistanceRejectionStrategy,
    TrendPullbackStrategy,
)

__all__ = [
    "Strategy",
    "StrategyContext",
    "StrategyResult",
    "StrategySelector",
    "TrendPullbackStrategy",
    "BreakoutRetestStrategy",
    "LiquiditySweepReversalStrategy",
    "RangeBreakoutStrategy",
    "SupportResistanceRejectionStrategy",
    "MomentumContinuationStrategy",
    "MeanReversionStrategy",
]
