from __future__ import annotations

import os
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from forex_intelligence.market_data import TwelveDataMarketDataProvider
from forex_intelligence.risk import SymbolSpec
from forex_intelligence.signal_pipeline import SignalPipeline
from forex_intelligence.strategy import StrategyContext
from forex_intelligence.telegram import TelegramNotifier

DEFAULT_SYMBOLS = ("EURUSD", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD", "XAUUSD")
NIGERIA_TZ = ZoneInfo("Africa/Lagos")
API_START = time(10, 0)
API_END = time(20, 0)


def _api_window_is_open(now: datetime) -> bool:
    local = now.astimezone(NIGERIA_TZ)
    return API_START <= local.time() < API_END


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


def _diagnose(pipeline: SignalPipeline, pair: str) -> str:
    """Explain the first production gate rejecting a symbol without relaxing it."""
    try:
        from forex_intelligence.domain import Timeframe
        snapshots = {tf: pipeline.provider.snapshot(pair, tf, 300) for tf in (Timeframe.H4, Timeframe.H1, Timeframe.M15)}
        unavailable = [tf.value for tf, snapshot in snapshots.items() if not snapshot.available or not snapshot.bars]
        if unavailable:
            return f"MARKET_DATA_UNAVAILABLE[{','.join(unavailable)}]"
        assessments = {tf: pipeline.regime_engine.assess(snapshot) for tf, snapshot in snapshots.items()}
        m15 = assessments[Timeframe.M15]
        if m15.regime.value == "UNTRADEABLE":
            return "UNTRADEABLE_REGIME"
        context = StrategyContext(
            pair=pair,
            regime=m15.regime.value,
            bars={tf.value: snapshot.bars for tf, snapshot in snapshots.items()},
            current_price=snapshots[Timeframe.M15].bars[-1].close,
            regimes={tf.value: assessment.regime.value for tf, assessment in assessments.items()},
        )
        selection = pipeline.strategy_selector.evaluate(context)
        if selection.selected is None:
            profile = pipeline.strategy_selector.profile
            assigned = profile.strategy_for(pair, context.regimes.get("M15", context.regime)) if profile else None
            if profile is not None and not assigned:
                return f"NO_VALIDATED_PROFILE[{context.regimes.get('M15', context.regime)}]"
            if not selection.candidates:
                return "NO_STRATEGY_CANDIDATE"
            return "STRATEGY_GATE_REJECTED"
        candidate = selection.selected
        if candidate.score < 80:
            return f"SCORE_BELOW_APPROVAL[{candidate.score:.1f}]"
        entry_quality = float((candidate.metadata or {}).get("entry_quality", 0.0))
        if entry_quality < 65:
            return f"ENTRY_QUALITY_BELOW_APPROVAL[{entry_quality:.1f}]"
        direction = candidate.direction
        aligned = {"STRONG_TREND_UP", "TREND_UP"} if direction == "BUY" else {"STRONG_TREND_DOWN", "TREND_DOWN"}
        if context.regimes.get("H1") not in aligned or context.regimes.get("H4") not in aligned:
            return f"MTF_MISALIGNMENT[M15={context.regimes.get('M15')},H1={context.regimes.get('H1')},H4={context.regimes.get('H4')}]"
        return "AWAITING_PRICE_TRIGGER"
    except Exception as exc:
        return f"DIAGNOSTIC_ERROR[{exc}]"


def main() -> int:
    now = datetime.now(timezone.utc)
    if not _api_window_is_open(now):
        local = now.astimezone(NIGERIA_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
        print(f"OUTSIDE_API_WINDOW: Nigeria={local} | allowed=10:00-20:00")
        return 0

    api_key = os.getenv("TWELVE_DATA_API_KEY")
    if not api_key:
        raise RuntimeError("TWELVE_DATA_API_KEY must be configured")
    notifier = TelegramNotifier()
    if not notifier.configured:
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be configured")

    equity = _env_float("SIGNAL_EQUITY", 1000.0)
    provider = TwelveDataMarketDataProvider(api_key)
    symbols = _symbols()
    trigger_confirmed = os.getenv("TRIGGER_CONFIRMED", "false").lower() == "true"
    print(f"SCANNING: {', '.join(symbols)}")
    print("API WINDOW: 10:00-20:00 Africa/Lagos")
    print(f"TRIGGER_MODE: {'EXTERNAL_CONFIRMATION' if trigger_confirmed else 'PRICE_TRIGGER_ONLY'}")
    failures = 0

    for symbol in symbols:
        spec = SymbolSpec(
            tick_size=_env_float(f"{symbol}_TICK_SIZE", _env_float("TICK_SIZE", 0.00001)),
            tick_value=_env_float(f"{symbol}_TICK_VALUE", _env_float("TICK_VALUE", 1.0)),
            volume_step=_env_float(f"{symbol}_VOLUME_STEP", _env_float("VOLUME_STEP", 0.01)),
            min_volume=_env_float(f"{symbol}_MIN_VOLUME", _env_float("MIN_VOLUME", 0.01)),
            max_volume=_env_float(f"{symbol}_MAX_VOLUME", _env_float("MAX_VOLUME", 100.0)),
        )
        pipeline = SignalPipeline(provider, notifier=notifier)
        try:
            signal, position = pipeline.evaluate_and_notify(pair=symbol, equity=equity, symbol_spec=spec, trigger_confirmed=trigger_confirmed, now=now)
        except Exception as exc:
            failures += 1
            print(f"ERROR: {symbol}: {exc}")
            continue
        if signal is None:
            print(f"NO_TRADE: {symbol} | REASON={_diagnose(pipeline, symbol)}")
            continue
        print(f"SIGNAL: {signal.direction.value} {signal.pair} entry={signal.entry} sl={signal.stop_loss} tp={signal.take_profit} volume={position.volume if position else 'n/a'}")

    if failures == len(symbols):
        raise RuntimeError("Scheduled scan failed for every configured symbol")
    if failures:
        print(f"PARTIAL_SCAN: {failures}/{len(symbols)} symbol failure(s); successful symbols completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
