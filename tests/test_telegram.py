import pytest

from forex_intelligence.telegram import (
    TelegramDeliveryError,
    TelegramNotifier,
    TelegramSignal,
    format_signal,
    signal_from_mapping,
)


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def send(self, token: str, chat_id: str, text: str) -> None:
        self.calls.append((token, chat_id, text))


def make_signal(**overrides: object) -> TelegramSignal:
    values = dict(
        pair="EURUSD",
        direction="BUY",
        status="TRIGGERED",
        strategy="Trend Pullback",
        regime="TREND_UP",
        entry="1.16280",
        stop_loss="1.16090",
        take_profit="1.16650",
        risk_reward="1:1.95",
        risk="0.5%",
        score=91,
        confidence="88%",
        timeframes="H4 bullish; H1 bullish; M15 confirmed",
        evidence="Higher-timeframe trend aligns with M15 structure",
        trigger="M15 confirmation above 1.16280",
        invalidation="M15 closes below 1.16090",
        expiry="2026-08-09T12:00:00Z",
    )
    values.update(overrides)
    return TelegramSignal(**values)


def test_format_contains_trade_details_and_manual_execution() -> None:
    text = format_signal(make_signal())
    assert "EURUSD" in text
    assert "BUY" in text
    assert "1.16090" in text
    assert "1.16650" in text
    assert "EXECUTION: MANUAL — Exness MT5" in text


def test_notifier_sends_using_configured_transport() -> None:
    transport = FakeTransport()
    notifier = TelegramNotifier("secret-token", "123", transport)
    notifier.send_signal(make_signal())
    assert len(transport.calls) == 1
    token, chat_id, text = transport.calls[0]
    assert token == "secret-token"
    assert chat_id == "123"
    assert "FOREX TRADE SIGNAL" in text


def test_notifier_rejects_missing_configuration() -> None:
    notifier = TelegramNotifier("", "", FakeTransport())
    with pytest.raises(TelegramDeliveryError, match="not configured"):
        notifier.send_signal(make_signal())


def test_notifier_rejects_no_trade_direction() -> None:
    notifier = TelegramNotifier("token", "chat", FakeTransport())
    with pytest.raises(TelegramDeliveryError, match="BUY/SELL"):
        notifier.send_signal(make_signal(direction="NO_TRADE"))


def test_signal_mapping_requires_complete_contract() -> None:
    with pytest.raises(ValueError, match="Signal is missing"):
        signal_from_mapping({"pair": "EURUSD"})


def test_signal_mapping_converts_exported_fields() -> None:
    source = {
        "pair": "EURUSD",
        "direction": "BUY",
        "status": "TRIGGERED",
        "strategy": "Trend Pullback",
        "market_regime": "TREND_UP",
        "entry": "1.16280",
        "stop_loss": "1.16090",
        "take_profit": "1.16650",
        "risk_reward": "1:1.95",
        "risk": "0.5%",
        "score": 91,
        "confidence": "88%",
        "timeframes": "H4/H1/M15",
        "evidence": "Trend aligned",
        "trigger": "M15 confirmation",
        "invalidation": "Below structure",
        "expiry": "2026-08-09T12:00:00Z",
    }
    signal = signal_from_mapping(source)
    assert signal.pair == "EURUSD"
    assert signal.score == 91
    assert signal.regime == "TREND_UP"
