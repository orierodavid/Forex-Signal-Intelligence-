"""Modular strategy framework for regime-aware setup detection."""

from .base import Strategy, StrategyContext, StrategyResult
from .evidence_selector import EvidenceAwareStrategySelector, EvidenceSelection
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
    "EvidenceAwareStrategySelector",
    "EvidenceSelection",
    "TrendPullbackStrategy",
    "BreakoutRetestStrategy",
    "LiquiditySweepReversalStrategy",
    "RangeBreakoutStrategy",
    "SupportResistanceRejectionStrategy",
    "MomentumContinuationStrategy",
    "MeanReversionStrategy",
]
