from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from forex_intelligence.domain.models import Direction, Evidence, MarketRegime, Signal, SignalStatus, Timeframe


def test_signal_contract_serializes_auditable_fields() -> None:
    now = datetime.now(timezone.utc)
    signal = Signal(
        signal_id=uuid4(), pair="eurusd", direction=Direction.BUY, strategy="Trend Pullback",
        market_regime=MarketRegime.TREND_UP, current_price=1.1, entry=1.101, stop_loss=1.099,
        take_profit=1.105, risk_reward=2.0, score=91, confidence=88,
        trigger="M15 close above 1.101", invalidation="M15 close below 1.099",
        expiry=now + timedelta(minutes=30), timeframes=(Timeframe.H4, Timeframe.H1, Timeframe.M15),
        evidence=(Evidence("HTF alignment", 0.95, 1.0, "H4/H1 structure"),), timestamp=now,
    )
    payload = signal.as_dict()
    assert payload["pair"] == "EURUSD"
    assert payload["direction"] == "BUY"
    assert payload["status"] == SignalStatus.WATCHING.value
    assert payload["evidence"][0]["source"] == "H4/H1 structure"


def test_signal_rejects_expired_definition() -> None:
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="expiry"):
        Signal(
            signal_id=uuid4(), pair="EURUSD", direction=Direction.BUY, strategy="Test",
            market_regime=MarketRegime.RANGE, current_price=1.1, entry=1.1, stop_loss=1.0,
            take_profit=1.2, risk_reward=1.0, score=50, confidence=50, trigger="x", invalidation="y",
            expiry=now, timeframes=(Timeframe.M15,), evidence=(), timestamp=now,
        )
