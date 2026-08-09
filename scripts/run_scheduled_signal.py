from __future__ import annotations

import os

from forex_intelligence.domain import Timeframe
from forex_intelligence.market_data import MT5MarketDataProvider
from forex_intelligence.risk import SymbolSpec
from forex_intelligence.signal_pipeline import SignalPipeline
from forex_intelligence.telegram import TelegramNotifier


def _env_float(name: str) -> float:
    value = os.getenv(name)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return float(value)


def main() -> int:
    symbol = os.getenv("FOREX_SYMBOL", "EURUSD")
    terminal_path = os.getenv("MT5_TERMINAL_PATH") or None
    notifier = TelegramNotifier()
    if not notifier.configured:
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be configured")

    provider = MT5MarketDataProvider(terminal_path=terminal_path)
    provider.connect()
    try:
        mt5 = provider._module()
        account = mt5.account_info()
        if account is None:
            raise RuntimeError(f"MT5 account_info failed: {mt5.last_error()}")

        info = mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError(f"MT5 symbol_info failed for {symbol}: {mt5.last_error()}")
        if not info.visible:
            if not mt5.symbol_select(symbol, True):
                raise RuntimeError(f"MT5 could not select symbol {symbol}")

        tick_size = float(getattr(info, "trade_tick_size", 0.0))
        tick_value = float(getattr(info, "trade_tick_value", 0.0))
        volume_step = float(getattr(info, "volume_step", 0.0))
        min_volume = float(getattr(info, "volume_min", 0.0))
        max_volume = float(getattr(info, "volume_max", 0.0))
        spec = SymbolSpec(tick_size, tick_value, volume_step, min_volume, max_volume)

        pipeline = SignalPipeline(provider, notifier=notifier)
        signal, position = pipeline.evaluate_and_notify(
            pair=symbol,
            equity=float(account.equity),
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
    finally:
        provider.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
