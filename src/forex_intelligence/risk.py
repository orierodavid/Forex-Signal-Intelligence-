from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class SymbolSpec:
    """Broker-supplied symbol economics required for position sizing."""
    tick_size: float
    tick_value: float
    volume_step: float
    min_volume: float
    max_volume: float

    def __post_init__(self) -> None:
        if self.tick_size <= 0 or self.tick_value <= 0:
            raise ValueError("tick_size and tick_value must be positive")
        if self.volume_step <= 0:
            raise ValueError("volume_step must be positive")
        if self.min_volume <= 0 or self.max_volume < self.min_volume:
            raise ValueError("invalid volume limits")


@dataclass(frozen=True)
class PositionSize:
    volume: float
    risk_amount: float
    stop_distance: float


class RiskEngine:
    """Calculates broker-aware position size without assuming pip economics."""
    def __init__(self, max_risk_per_trade: float = 0.005) -> None:
        if not 0 < max_risk_per_trade <= 1:
            raise ValueError("max_risk_per_trade must be between 0 and 1")
        self.max_risk_per_trade = max_risk_per_trade

    def calculate_position_size(self, *, equity: float, entry: float,
                                stop_loss: float, symbol: SymbolSpec,
                                risk_fraction: float | None = None) -> PositionSize:
        if equity <= 0:
            raise ValueError("equity must be positive")
        if entry <= 0 or stop_loss <= 0:
            raise ValueError("entry and stop_loss must be positive")
        if entry == stop_loss:
            raise ValueError("entry and stop_loss must differ")
        fraction = self.max_risk_per_trade if risk_fraction is None else risk_fraction
        if not 0 < fraction <= self.max_risk_per_trade:
            raise ValueError("risk_fraction exceeds configured maximum")
        stop_distance = abs(entry - stop_loss)
        risk_amount = equity * fraction
        loss_per_volume = stop_distance / symbol.tick_size * symbol.tick_value
        if loss_per_volume <= 0:
            raise ValueError("calculated loss per volume must be positive")
        raw_volume = risk_amount / loss_per_volume
        volume = math.floor(raw_volume / symbol.volume_step) * symbol.volume_step
        volume = min(volume, symbol.max_volume)
        if volume < symbol.min_volume:
            raise ValueError("required position size is below broker minimum volume")
        precision = max(0, int(round(-math.log10(symbol.volume_step))))
        volume = round(volume, precision)
        actual_risk = volume * loss_per_volume
        if actual_risk > risk_amount + 1e-12:
            volume = round(volume - symbol.volume_step, precision)
        if volume < symbol.min_volume:
            raise ValueError("minimum broker volume would exceed the risk budget")
        return PositionSize(volume=volume, risk_amount=volume * loss_per_volume,
                            stop_distance=stop_distance)
