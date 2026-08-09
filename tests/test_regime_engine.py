from datetime import datetime, timedelta, timezone

from forex_intelligence.domain import MarketRegime, Timeframe
from forex_intelligence.market_data.models import Bar, MarketSnapshot
from forex_intelligence.regime import RegimeEngine


def make_snapshot(closes: list[float]) -> MarketSnapshot:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = tuple(
        Bar(
            symbol="EURUSD",
            timeframe=Timeframe.H1,
            timestamp=start + timedelta(hours=i),
            open=price - 0.0001,
            high=price + 0.0005,
            low=price - 0.0005,
            close=price,
        )
        for i, price in enumerate(closes)
    )
    return MarketSnapshot("EURUSD", Timeframe.H1, bars, "HISTORICAL", "test", start)


def test_insufficient_data_is_untradeable() -> None:
    assessment = RegimeEngine().assess(make_snapshot([1.1 + i * 0.0001 for i in range(20)]))
    assert assessment.regime == MarketRegime.UNTRADEABLE


def test_uptrend_is_directional() -> None:
    closes = [1.1000 + i * 0.0008 for i in range(100)]
    assessment = RegimeEngine().assess(make_snapshot(closes))
    assert assessment.regime in {MarketRegime.TREND_UP, MarketRegime.STRONG_TREND_UP}
    assert assessment.metrics.ema_fast > assessment.metrics.ema_slow


def test_downtrend_is_directional() -> None:
    closes = [1.1800 - i * 0.0008 for i in range(100)]
    assessment = RegimeEngine().assess(make_snapshot(closes))
    assert assessment.regime in {MarketRegime.TREND_DOWN, MarketRegime.STRONG_TREND_DOWN}
    assert assessment.metrics.ema_fast < assessment.metrics.ema_slow


def test_forming_bar_is_excluded() -> None:
    closes = [1.1000 + i * 0.0003 for i in range(100)]
    snapshot = make_snapshot(closes)
    original = RegimeEngine().assess(snapshot)
    altered = list(snapshot.bars)
    last = altered[-1]
    altered[-1] = Bar(last.symbol, last.timeframe, last.timestamp, last.open, last.high + 1, last.low - 1, last.close - 1)
    modified = MarketSnapshot(snapshot.symbol, snapshot.timeframe, tuple(altered), snapshot.quality, snapshot.provider, snapshot.retrieved_at)
    assert RegimeEngine().assess(modified).metrics == original.metrics


def test_unavailable_snapshot_is_untradeable() -> None:
    snapshot = MarketSnapshot("EURUSD", Timeframe.H4, (), "UNAVAILABLE", "mt5", datetime.now(timezone.utc), "provider down")
    assessment = RegimeEngine().assess(snapshot)
    assert assessment.regime == MarketRegime.UNTRADEABLE
    assert assessment.tradable is False
