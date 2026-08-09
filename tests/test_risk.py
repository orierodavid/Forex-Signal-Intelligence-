import pytest

from forex_intelligence.risk import PositionSize, RiskEngine, SymbolSpec


def spec():
    return SymbolSpec(tick_size=0.00001, tick_value=1.0, volume_step=0.01,
                      min_volume=0.01, max_volume=100.0)


def test_position_size_uses_tick_economics():
    result = RiskEngine(0.005).calculate_position_size(
        equity=10_000, entry=1.10000, stop_loss=1.09900, symbol=spec()
    )
    assert isinstance(result, PositionSize)
    assert result.volume == pytest.approx(0.5)
    assert result.risk_amount == pytest.approx(50.0)


def test_position_size_never_exceeds_configured_risk():
    result = RiskEngine(0.005).calculate_position_size(
        equity=10_000, entry=1.10000, stop_loss=1.09933, symbol=spec()
    )
    assert result.risk_amount <= 50.0 + 1e-9


def test_rejects_below_minimum_volume():
    with pytest.raises(ValueError, match="below broker minimum"):
        RiskEngine(0.005).calculate_position_size(
            equity=100, entry=1.10000, stop_loss=1.09000, symbol=spec()
        )


def test_rejects_excess_requested_risk():
    with pytest.raises(ValueError, match="exceeds configured maximum"):
        RiskEngine(0.005).calculate_position_size(
            equity=10_000, entry=1.10000, stop_loss=1.09900,
            symbol=spec(), risk_fraction=0.01
        )


def test_rejects_zero_stop_distance():
    with pytest.raises(ValueError, match="must differ"):
        RiskEngine().calculate_position_size(
            equity=10_000, entry=1.10000, stop_loss=1.10000, symbol=spec()
        )
