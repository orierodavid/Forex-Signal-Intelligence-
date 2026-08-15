from datetime import datetime, timedelta, timezone

from forex_intelligence.domain import Timeframe
from forex_intelligence.market_data import MarketSnapshot
from forex_intelligence.market_data.models import Bar
from forex_intelligence.risk import SymbolSpec
from forex_intelligence.signal_pipeline import SignalPipeline
from forex_intelligence.telegram import TelegramNotifier


class FakeProvider:
    def __init__(self, bars):
        self.bars = bars

    def snapshot(self, symbol, timeframe, count=300):
        return MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            bars=tuple(self.bars),
            quality="SIMULATED",
            provider="test-fixture",
            retrieved_at=datetime.now(timezone.utc),
        )


class FakeTransport:
    def __init__(self):
        self.calls = []

    def send(self, token, chat_id, text):
        self.calls.append((token, chat_id, text))


def make_bars(count=100):
    start = datetime(2026, 8, 9, 8, 0, tzinfo=timezone.utc)
    bars = []
    for i in range(count):
        close = 1.1000 + i * 0.0002
        bars.append(
            Bar(
                symbol="EURUSD",
                timeframe=Timeframe.M15,
                timestamp=start + timedelta(minutes=15 * i),
                open=close - 0.00005,
                high=close + 0.00008,
                low=close - 0.00008,
                close=close,
                quality="SIMULATED",
            )
        )
    return bars


def test_real_analysis_path_reaches_telegram_without_broker_execution():
    transport = FakeTransport()
    notifier = TelegramNotifier("token", "chat", transport)
    pipeline = SignalPipeline(FakeProvider(make_bars()), notifier=notifier)

    signal, position = pipeline.evaluate_and_notify(
        pair="EURUSD",
        equity=10_000,
        symbol_spec=SymbolSpec(
            tick_size=0.00001,
            tick_value=1.0,
            volume_step=0.01,
            min_volume=0.01,
            max_volume=100.0,
        ),
        trigger_confirmed=True,
        # Keep the fixture deterministic and explicitly inside the FX session.
        now=datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc),
    )

    assert signal is not None
    assert signal.direction.value == "BUY"
    assert signal.status.value == "TRIGGERED"
    assert position is not None
    assert len(transport.calls) == 1
    message = transport.calls[0][2]
    assert "EURUSD" in message
    assert "DIRECTION: BUY" in message
    assert "EXECUTION: MANUAL — Exness MT5" in message


def test_pipeline_does_not_emit_alert_without_explicit_trigger():
    transport = FakeTransport()
    notifier = TelegramNotifier("token", "chat", transport)
    pipeline = SignalPipeline(FakeProvider(make_bars()), notifier=notifier)

    signal, position = pipeline.evaluate_and_notify(
        pair="EURUSD",
        equity=10_000,
        symbol_spec=SymbolSpec(
            tick_size=0.00001,
            tick_value=1.0,
            volume_step=0.01,
            min_volume=0.01,
            max_volume=100.0,
        ),
        trigger_confirmed=False,
        now=datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc),
    )

    assert signal is None
    assert position is None
    assert transport.calls == []


def test_pipeline_suppresses_signals_when_weekly_fx_market_is_closed():
    transport = FakeTransport()
    notifier = TelegramNotifier("token", "chat", transport)
    pipeline = SignalPipeline(FakeProvider(make_bars()), notifier=notifier)

    signal, position = pipeline.evaluate_and_notify(
        pair="EURUSD",
        equity=10_000,
        symbol_spec=SymbolSpec(
            tick_size=0.00001,
            tick_value=1.0,
            volume_step=0.01,
            min_volume=0.01,
            max_volume=100.0,
        ),
        trigger_confirmed=True,
        now=datetime(2026, 8, 15, 10, 0, tzinfo=timezone.utc),
    )

    assert signal is None
    assert position is None
    assert transport.calls == []
