from __future__ import annotations

from collections.abc import Mapping

from .telegram import TelegramNotifier, signal_from_mapping


class SignalOutput:
    """Final output boundary for qualified trade signals.

    Broker execution is intentionally outside this boundary. A qualified
    signal is converted to the Telegram contract and delivered to the user
    for manual execution in Exness MT5.
    """

    def __init__(self, telegram: TelegramNotifier) -> None:
        self.telegram = telegram

    def publish(self, signal: Mapping[str, object]) -> bool:
        """Publish one qualified signal to Telegram.

        Returns True only after Telegram accepts the message. The method does
        not submit, modify, or close broker orders.
        """
        normalized = signal_from_mapping(signal)
        self.telegram.send_signal(normalized)
        return True


def publish_signal(signal: Mapping[str, object], telegram: TelegramNotifier | None = None) -> bool:
    """Convenience entry point for the analysis pipeline."""
    return SignalOutput(telegram or TelegramNotifier()).publish(signal)
