import pytest

from forex_intelligence.signal_output import SignalOutput
from forex_intelligence.telegram import TelegramDeliveryError, TelegramNotifier


class FakeTransport:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, str]] = []

    def send(self, token: str, chat_id: str, text: str) -> None:
        self.messages.append((token, chat_id, text))


def qualified_signal() -> dict[str, object]:
    return {
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
        "timeframes": "H4 bullish; H1 bullish; M15 confirmed",
        "evidence": "Higher-timeframe trend aligns with M15 structure",
        "trigger": "M15 confirmation above 1.16280",
        "invalidation": "M15 closes below 1.16090",
        "expiry": "2026-08-09T12:00:00Z",
    }


def test_signal_output_publishes_only_to_telegram() -> None:
    transport = FakeTransport()
    notifier = TelegramNotifier("token", "chat", transport)

    assert SignalOutput(notifier).publish(qualified_signal()) is True
    assert len(transport.messages) == 1
    assert "EURUSD" in transport.messages[0][2]
    assert "EXECUTION: MANUAL — Exness MT5" in transport.messages[0][2]


def test_signal_output_fails_closed_without_telegram_configuration() -> None:
    notifier = TelegramNotifier("", "", FakeTransport())
    with pytest.raises(TelegramDeliveryError):
        SignalOutput(notifier).publish(qualified_signal())


def test_signal_output_rejects_incomplete_signal() -> None:
    transport = FakeTransport()
    notifier = TelegramNotifier("token", "chat", transport)
    with pytest.raises(ValueError):
        SignalOutput(notifier).publish({"pair": "EURUSD", "direction": "BUY"})
