from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Mapping, Protocol


class TelegramDeliveryError(RuntimeError):
    """Raised when Telegram cannot accept a notification."""


class TelegramTransport(Protocol):
    def send(self, token: str, chat_id: str, text: str) -> None: ...


class HttpTelegramTransport:
    """Minimal dependency-free Telegram Bot API transport."""

    def __init__(self, timeout_seconds: float = 10.0) -> None:
        self.timeout_seconds = timeout_seconds

    def send(self, token: str, chat_id: str, text: str) -> None:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = urllib.parse.urlencode(
            {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}
        ).encode("utf-8")
        request = urllib.request.Request(url, data=payload, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise TelegramDeliveryError("Telegram delivery failed") from exc
        if not body.get("ok"):
            raise TelegramDeliveryError("Telegram rejected the notification")


@dataclass(frozen=True)
class TelegramSignal:
    pair: str
    direction: str
    status: str
    strategy: str
    regime: str
    entry: str
    stop_loss: str
    take_profit: str
    risk_reward: str
    risk: str
    score: int
    confidence: str
    timeframes: str
    evidence: str
    trigger: str
    invalidation: str
    expiry: str


class TelegramNotifier:
    """Final signal output. Never performs broker execution."""

    def __init__(self, token: str | None = None, chat_id: str | None = None, transport: TelegramTransport | None = None) -> None:
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self.transport = transport or HttpTelegramTransport()

    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def send_signal(self, signal: TelegramSignal) -> None:
        if not self.configured:
            raise TelegramDeliveryError("Telegram is not configured")
        if signal.direction not in {"BUY", "SELL"}:
            raise TelegramDeliveryError("Only BUY/SELL signals may be sent as trade alerts")
        self.transport.send(self.token, self.chat_id, format_signal(signal))


def format_signal(signal: TelegramSignal) -> str:
    return "\n".join(
        (
            "⚡ FOREX TRADE SIGNAL",
            "",
            f"PAIR: {signal.pair}",
            f"DIRECTION: {signal.direction}",
            f"STATUS: {signal.status}",
            "",
            f"Strategy: {signal.strategy}",
            f"Regime: {signal.regime}",
            f"Entry: {signal.entry}",
            f"Stop Loss: {signal.stop_loss}",
            f"Take Profit: {signal.take_profit}",
            f"Risk/Reward: {signal.risk_reward}",
            f"Risk: {signal.risk}",
            f"Score: {signal.score}/100",
            f"Confidence: {signal.confidence}",
            "",
            f"Timeframes: {signal.timeframes}",
            f"Evidence: {signal.evidence}",
            "",
            f"Trigger: {signal.trigger}",
            f"Invalidation: {signal.invalidation}",
            f"Expiry: {signal.expiry}",
            "",
            "EXECUTION: MANUAL — Exness MT5",
            "",
            "This is a probabilistic signal, not a guarantee.",
        )
    )


def signal_from_mapping(values: Mapping[str, object]) -> TelegramSignal:
    """Convert an exported signal mapping without coupling the notifier to strategy models."""
    required = {
        "pair", "direction", "status", "strategy", "market_regime", "entry",
        "stop_loss", "take_profit", "risk_reward", "risk", "score", "confidence",
        "timeframes", "evidence", "trigger", "invalidation", "expiry",
    }
    missing = sorted(key for key in required if key not in values)
    if missing:
        raise ValueError(f"Signal is missing required fields: {', '.join(missing)}")
    return TelegramSignal(
        pair=str(values["pair"]),
        direction=str(values["direction"]),
        status=str(values["status"]),
        strategy=str(values["strategy"]),
        regime=str(values["market_regime"]),
        entry=str(values["entry"]),
        stop_loss=str(values["stop_loss"]),
        take_profit=str(values["take_profit"]),
        risk_reward=str(values["risk_reward"]),
        risk=str(values["risk"]),
        score=int(values["score"]),
        confidence=str(values["confidence"]),
        timeframes=str(values["timeframes"]),
        evidence=str(values["evidence"]),
        trigger=str(values["trigger"]),
        invalidation=str(values["invalidation"]),
        expiry=str(values["expiry"]),
    )
