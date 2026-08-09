"""Run one scheduled signal cycle and deliver only qualified trade signals to Telegram.

This is deliberately a single-cycle runner. Scheduling is provided by the hosting
platform; this script never submits broker orders.
"""
from __future__ import annotations

import os
import sys
from typing import Any

from forex_intelligence.telegram import TelegramNotifier, signal_from_mapping


def deliver_qualified_signal(signal: dict[str, Any], notifier: TelegramNotifier) -> bool:
    """Send a validated trade signal to Telegram; return False for non-trade output."""
    if signal.get("status") not in {"TRIGGERED", "READY"}:
        return False
    if signal.get("direction") not in {"BUY", "SELL"}:
        return False
    notifier.send_signal(signal_from_mapping(signal))
    return True


def main() -> int:
    # The actual market/strategy pipeline is injected by the application runtime.
    # This guard prevents accidental execution if someone runs this scaffold without
    # wiring a producer. Broker execution is intentionally absent from this runner.
    if os.getenv("SIGNAL_CYCLE_ENABLED", "false").lower() != "true":
        print("Signal cycle disabled; no trade signal delivered.")
        return 0

    print("Signal cycle enabled. Connect the production signal producer before scheduling.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
