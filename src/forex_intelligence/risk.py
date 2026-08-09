from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR


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

    def calculate_position_size(
        self,
        *,
        equity: float,
        entry: float,
        stop_loss: float,
        symbol: SymbolSpec,
        risk_fraction: float | None = None,
    ) -> PositionSize:
        if equity <= 0:
            raise ValueError("equity must be positive")
        if entry <= 0 or stop_loss <= 0:
            raise ValueError("entry and stop_loss must be positive")
        if entry == stop_loss:
            raise ValueError("entry and stop_loss must differ")

        fraction = self.max_risk_per_trade if risk_fraction is None else risk_fraction
        if not 0 < fraction <= self.max_risk_per_trade:
            raise ValueError("risk_fraction exceeds configured maximum")

        # Use Decimal for price/tick arithmetic so exact broker step boundaries
        # are not lost to binary floating-point representation.
        entry_d = Decimal(str(entry))
        stop_d = Decimal(str(stop_loss))
        tick_size_d = Decimal(str(symbol.tick_size))
        tick_value_d = Decimal(str(symbol.tick_value))
        step_d = Decimal(str(symbol.volume_step))
        equity_d = Decimal(str(equity))
        fraction_d = Decimal(str(fraction))

        stop_distance_d = abs(entry_d - stop_d)
        risk_amount_d = equity_d * fraction_d
        loss_per_volume_d = (stop_distance_d / tick_size_d) * tick_value_d
        if loss_per_volume_d <= 0:
            raise ValueError("calculated loss per volume must be positive")

        raw_volume_d = risk_amount_d / loss_per_volume_d
        steps = (raw_volume_d / step_d).to_integral_value(rounding=ROUND_FLOOR)
        volume_d = min(steps * step_d, Decimal(str(symbol.max_volume)))

        if volume_d < Decimal(str(symbol.min_volume)):
            raise ValueError("required position size is below broker minimum volume")

        actual_risk_d = volume_d * loss_per_volume_d
        if actual_risk_d > risk_amount_d:
            volume_d -= step_d
        if volume_d < Decimal(str(symbol.min_volume)):
            raise ValueError("minimum broker volume would exceed the risk budget")

        return PositionSize(
            volume=float(volume_d),
            risk_amount=float(volume_d * loss_per_volume_d),
            stop_distance=float(stop_distance_d),
        )
