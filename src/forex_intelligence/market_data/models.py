from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from forex_intelligence.domain import Timeframe

DataQuality = Literal["REAL", "HISTORICAL", "SIMULATED", "UNAVAILABLE"]


@dataclass(frozen=True, slots=True)
class Bar:
    symbol: str
    timeframe: Timeframe
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    tick_volume: int = 0
    spread_points: int = 0
    real_volume: int = 0
    quality: DataQuality = "REAL"

    def __post_init__(self) -> None:
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("OHLC values are internally inconsistent")
        if self.low > self.high:
            raise ValueError("low cannot exceed high")


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    symbol: str
    timeframe: Timeframe
    bars: tuple[Bar, ...]
    quality: DataQuality
    provider: str
    retrieved_at: datetime
    error: str | None = None

    @property
    def available(self) -> bool:
        return bool(self.bars) and self.quality != "UNAVAILABLE" and self.error is None
