from forex_intelligence.backtest import BacktestReport, BacktestTrade, Candle, run_backtest


def _bars(count=80):
    bars = []
    price = 1.1000
    for i in range(count):
        close = price + 0.0005
        bars.append(Candle(
            timestamp=f"2026-01-01T{i:04d}:00",
            open=price,
            high=close + 0.0002,
            low=price - 0.0001,
            close=close,
        ))
        price = close
    return bars


def test_backtest_report_metrics_are_deterministic():
    report = BacktestReport(
        pair="EURUSD",
        trades=(
            BacktestTrade("EURUSD", "t1", "X", "BUY", 82, 1.1, 1.0, 1.3, 2.0),
            BacktestTrade("EURUSD", "t2", "X", "BUY", 78, 1.2, 1.3, 1.0, -1.0),
        ),
    )
    assert report.total_trades == 2
    assert report.wins == 1
    assert report.losses == 1
    assert report.win_rate == 50.0
    assert report.net_r == 1.0
    assert report.profit_factor == 2.0


def test_backtest_replays_closed_candles_and_produces_report():
    report = run_backtest("EURUSD", _bars())
    assert report.pair == "EURUSD"
    assert report.total_trades >= 0
    for trade in report.trades:
        assert trade.score >= 70
        assert trade.direction in {"BUY", "SELL"}
        assert trade.entry > 0
        assert trade.stop_loss > 0
        assert trade.take_profit > 0
