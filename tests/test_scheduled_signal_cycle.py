from scripts.run_scheduled_signal_cycle import deliver_qualified_signal
from forex_intelligence.telegram import TelegramNotifier


class FakeTransport:
    def __init__(self):
        self.calls = []

    def send(self, token, chat_id, text):
        self.calls.append((token, chat_id, text))


def signal(status="TRIGGERED", direction="BUY"):
    return {
        "pair": "EURUSD", "direction": direction, "status": status,
        "strategy": "Trend Pullback", "market_regime": "TREND_UP",
        "entry": "1.16280", "stop_loss": "1.16090", "take_profit": "1.16650",
        "risk_reward": "1:1.95", "risk": "0.5%", "score": 91, "confidence": "88%",
        "timeframes": "H4/H1/M15", "evidence": "Trend aligned",
        "trigger": "M15 confirmation", "invalidation": "Below structure",
        "expiry": "2026-08-09T12:00:00Z",
    }


def test_qualified_signal_is_delivered_to_telegram():
    transport = FakeTransport()
    notifier = TelegramNotifier("token", "chat", transport)
    assert deliver_qualified_signal(signal(), notifier) is True
    assert len(transport.calls) == 1
    assert "EURUSD" in transport.calls[0][2]


def test_non_trade_signal_is_not_delivered():
    transport = FakeTransport()
    notifier = TelegramNotifier("token", "chat", transport)
    assert deliver_qualified_signal(signal(status="WATCHING"), notifier) is False
    assert transport.calls == []


def test_invalid_direction_is_not_delivered():
    transport = FakeTransport()
    notifier = TelegramNotifier("token", "chat", transport)
    assert deliver_qualified_signal(signal(direction="NO_TRADE"), notifier) is False
    assert transport.calls == []
