from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from forex_intelligence.market_data import TwelveDataMarketDataProvider
from forex_intelligence.risk import SymbolSpec
from forex_intelligence.signal_pipeline import SignalPipeline
from forex_intelligence.telegram import TelegramNotifier

DEFAULT_SYMBOLS = ("EURUSD", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD", "XAUUSD")
STATE_PATH = Path(os.getenv("SCHEDULER_STATE_PATH", ".cache/scheduler_state.json"))


def _env_float(name: str, default: float | None = None) -> float:
    value = os.getenv(name)
    if value is None:
        if default is None:
            raise RuntimeError(f"Missing required environment variable: {name}")
        return default
    return float(value)


def _symbols() -> tuple[str, ...]:
    configured = os.getenv("FOREX_SYMBOLS")
    if not configured:
        return DEFAULT_SYMBOLS
    symbols = tuple(item.strip().upper() for item in configured.split(",") if item.strip())
    if not symbols:
        raise RuntimeError("FOREX_SYMBOLS must contain at least one symbol")
    return symbols


def _load_state() -> dict[str, str]:
    try:
        return json.loads(STATE_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(state: dict[str, str]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def _latest_m15_timestamp(provider: TwelveDataMarketDataProvider, symbol: str) -> str:
    """Read the latest M15 candle timestamp without running the signal engine."""
    snapshot = provider.snapshot(symbol, "M15", 2)
    if not snapshot.bars:
        raise RuntimeError(f"No M15 bars returned for {symbol}")
    return snapshot.bars[-1].timestamp.isoformat()


def main() -> int:
    api_key = os.getenv("TWELVE_DATA_API_KEY")
    if not api_key:
        raise RuntimeError("TWELVE_DATA_API_KEY must be configured")

    notifier = TelegramNotifier()
    if not notifier.configured:
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be configured")

    equity = _env_float("SIGNAL_EQUITY", 1000.0)
    provider = TwelveDataMarketDataProvider(api_key)
    symbols = _symbols()
    state = _load_state()

    print(f"SCANNING: {', '.join(symbols)}")
    failures = 0
    skipped = 0

    for symbol in symbols:
        try:
            latest_bar = _latest_m15_timestamp(provider, symbol)
        except Exception as exc:
            failures += 1
            print(f"ERROR: {symbol}: {exc}")
            continue

        # The scheduler polls more frequently than M15, but the strategy is
        # evaluated only once per newly observed M15 bar. This compensates for
        # GitHub Actions' non-deterministic cron start time without repeatedly
        # sending the same M15 setup.
        if state.get(symbol) == latest_bar:
            skipped += 1
            print(f"WAIT_M15: {symbol} | bar={latest_bar}")
            continue

        # These are reference risk-account parameters, not broker credentials.
        spec = SymbolSpec(
            tick_size=_env_float(f"{symbol}_TICK_SIZE", _env_float("TICK_SIZE", 0.00001)),
            tick_value=_env_float(f"{symbol}_TICK_VALUE", _env_float("TICK_VALUE", 1.0)),
            volume_step=_env_float(f"{symbol}_VOLUME_STEP", _env_float("VOLUME_STEP", 0.01)),
            min_volume=_env_float(f"{symbol}_MIN_VOLUME", _env_float("MIN_VOLUME", 0.01)),
            max_volume=_env_float(f"{symbol}_MAX_VOLUME", _env_float("MAX_VOLUME", 100.0)),
        )

        pipeline = SignalPipeline(provider, notifier=notifier)
        try:
            signal, position = pipeline.evaluate_and_notify(
                pair=symbol,
                equity=equity,
                symbol_spec=spec,
                trigger_confirmed=os.getenv("TRIGGER_CONFIRMED", "false").lower() == "true",
                now=datetime.now(timezone.utc),
            )
        except Exception as exc:
            failures += 1
            print(f"ERROR: {symbol}: {exc}")
            continue

        # Mark the M15 bar as processed only after the analysis completed.
        # Thus a transient provider/analysis failure can be retried on the next
        # poll instead of permanently losing that candle.
        state[symbol] = latest_bar
        _save_state(state)

        if signal is None:
            print(f"NO_TRADE: {symbol}")
            continue

        print(
            f"SIGNAL: {signal.direction.value} {signal.pair} "
            f"entry={signal.entry} sl={signal.stop_loss} tp={signal.take_profit} "
            f"volume={position.volume if position else 'n/a'}"
        )

    if failures == len(symbols):
        raise RuntimeError("All configured symbols failed during the scheduled scan")
    if skipped == len(symbols):
        print("NO_NEW_M15_BARS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
