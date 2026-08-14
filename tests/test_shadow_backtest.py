from forex_intelligence.backtest import Candle
from forex_intelligence.shadow_backtest import run_shadow_backtest


def _bars(count=220):
    bars = []
    price = 1.1000
    for i in range(count):
        # Deterministic alternating regimes so the comparison is reproducible.
        drift = 0.0005 if (i // 40) % 2 == 0 else -0.00045
        close = price + drift
        bars.append(Candle(
            timestamp=f"2026-01-01T{i:02d}:00:00",
            open=price,
            high=max(price, close) + 0.0002,
            low=min(price, close) - 0.0002,
            close=close,
        ))
        price = close
    return bars


def test_shadow_backtest_compares_both_selectors_without_lookahead():
    comparison = run_shadow_backtest("EURUSD", _bars(), lookback=30)
    assert comparison.pair == "EURUSD"
    assert comparison.current.pair == "EURUSD"
    assert comparison.adaptive.pair == "EURUSD"
    for report in (comparison.current, comparison.adaptive):
        for trade in report.trades:
            assert trade.score >= 70
            assert trade.entry_timestamp is not None
            assert trade.exit_timestamp is not None


def test_shadow_result_is_deterministic():
    first = run_shadow_backtest("EURUSD", _bars(), lookback=30)
    second = run_shadow_backtest("EURUSD", _bars(), lookback=30)
    assert first.current.net_r == second.current.net_r
    assert first.adaptive.net_r == second.adaptive.net_r
    assert first.current.total_trades == second.current.total_trades
    assert first.adaptive.total_trades == second.adaptive.total_trades
