from forex_intelligence.backtest import BacktestTrade


def test_backtest_trade_records_pending_entry_before_exit():
    trade = BacktestTrade(
        "EURUSD",
        "2026-01-01T00:00:00",
        "BREAKOUT",
        "BUY",
        82,
        1.1000,
        1.0980,
        1.1040,
        2.0,
        exit_timestamp="2026-01-01T01:00:00",
        entry_timestamp="2026-01-01T00:30:00",
    )
    assert trade.entry_timestamp > trade.timestamp
    assert trade.exit_timestamp > trade.entry_timestamp
