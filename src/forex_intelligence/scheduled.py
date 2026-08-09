from __future__ import annotations

from typing import Any

from .telegram import TelegramNotifier, signal_from_mapping


def deliver_qualified_signal(signal: dict[str, Any], notifier: TelegramNotifier) -> bool:
    """Deliver only a qualified BUY/SELL signal to Telegram.

    This module is part of the installable application package so CI and the
    production runner use the same import path. It never submits broker orders.
    """
    if signal.get("status") not in {"TRIGGERED", "READY"}:
        return False
    if signal.get("direction") not in {"BUY", "SELL"}:
        return False
    notifier.send_signal(signal_from_mapping(signal))
    return True
