from __future__ import annotations

from typing import Any, Callable

from forex_intelligence.telegram import TelegramNotifier, signal_from_mapping


SignalProducer = Callable[[], dict[str, Any] | None]


def deliver_qualified_signal(signal: dict[str, Any], notifier: TelegramNotifier) -> bool:
    """Deliver only a qualified BUY/SELL signal; never execute a broker order."""
    if signal.get("status") not in {"TRIGGERED", "READY"}:
        return False
    if signal.get("direction") not in {"BUY", "SELL"}:
        return False
    notifier.send_signal(signal_from_mapping(signal))
    return True


def run_cycle(producer: SignalProducer, notifier: TelegramNotifier) -> bool:
    """Run one scheduled producer cycle and send its qualified output to Telegram."""
    signal = producer()
    if signal is None:
        return False
    return deliver_qualified_signal(signal, notifier)
