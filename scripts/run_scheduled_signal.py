from __future__ import annotations

import os

from forex_intelligence.market_data import TwelveDataMarketDataProvider
from forex_intelligence.risk import SymbolSpec
from forex_intelligence.signal_pipeline import SignalPipeline
from forex_intelligence.telegram import TelegramNotifier


def _env_float(name: str, default: float | None = None) -> float:
    value = os.getenv(name)
    if value is None:
        if default is None:
            raise RuntimeError(f"Missing required environment variable: {name}")
        return default
    return float(value)


def main() -> int:
    symbol = os.getenv("FOREX_SYMBOL", "EURUSD")
    api_key = os.getenv("TWELVE_DATA_API_KEY")
    if not api_key:
        raise RuntimeError("TWELVE_DATA_API_KEY must be configured")

    notifier = TelegramNotifier()
    if not notifier.configured:
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be configured")

    # These are reference risk-account parameters, not broker credentials.
    # They allow the cloud scheduler to calculate a consistent position size
    # without connecting to or executing against an Exness account.
    equity = _env_float("SIGNAL_EQUITY", 1000.0)
    spec = SymbolSpec(
        tick_size=_env_float("TICK_SIZE", 0.00001),
        tick_value=_env_float("TICK_VALUE", 1.0),
        volume_step=_env_float("VOLUME_STEP", 0.01),
        min_volume=_env_float("MIN_VOLUME", 0.01),
        max_volume=_env_float("MAX_VOLUME", 100.0),
    )

    provider = TwelveDataMarketDataProvider(api_key)
    pipeline = SignalPipeline(provider, notifier=notifier)
    signal, position = pipeline.evaluate_and_notify(
        pair=symbol,
        equity=equity,
        symbol_spec=spec,
        trigger_confirmed=os.getenv("TRIGGER_CONFIRMED", "false").lower() == "true",
    )
    if signal is None:
        print(f"NO_TRADE: {symbol}")
        return 0

    print(
        f"SIGNAL: {signal.direction.value} {signal.pair} "
        f"entry={signal.entry} sl={signal.stop_loss} tp={signal.take_profit} "
        f"volume={position.volume if position else 'n/a'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
