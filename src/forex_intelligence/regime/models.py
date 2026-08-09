from dataclasses import dataclass

from forex_intelligence.domain import MarketRegime, Timeframe


@dataclass(frozen=True, slots=True)
class RegimeMetrics:
    ema_fast: float
    ema_slow: float
    atr: float
    atr_percent: float
    adx: float
    directional_score: float
    compression_ratio: float


@dataclass(frozen=True, slots=True)
class RegimeAssessment:
    symbol: str
    timeframe: Timeframe
    regime: MarketRegime
    confidence: float
    metrics: RegimeMetrics
    reasons: tuple[str, ...]

    @property
    def tradable(self) -> bool:
        return self.regime != MarketRegime.UNTRADEABLE
