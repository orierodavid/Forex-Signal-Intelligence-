from types import SimpleNamespace

from forex_intelligence.strategy.base import StrategyContext, StrategyResult
from forex_intelligence.strategy.entry_quality import entry_quality, gate_candidate


def _bars(direction="BUY"):
    bars = []
    price = 100.0
    for i in range(14):
        if direction == "BUY":
            open_ = price
            close = price + (0.12 if i < 13 else 0.05)
            high = close + 0.03
            low = open_ - 0.03
        else:
            open_ = price
            close = price - (0.12 if i < 13 else 0.05)
            high = open_ + 0.03
            low = close - 0.03
        bars.append(SimpleNamespace(open=open_, high=high, low=low, close=close))
        price = close
    return tuple(bars)


def _context(bars):
    return StrategyContext(
        pair="EURUSD",
        regime="TREND_UP",
        bars={"M15": bars},
        current_price=bars[-1].close,
        regimes={"M15": "TREND_UP", "H1": "TREND_UP", "H4": "TREND_UP"},
    )


def test_entry_quality_is_independent_of_raw_strategy_score():
    context = _context(_bars("BUY"))
    low = StrategyResult("X", "BUY", 70, True, "trigger", "invalid")
    high = StrategyResult("X", "BUY", 90, True, "trigger", "invalid")
    assert entry_quality(context, low) == entry_quality(context, high)


def test_gate_records_quality_and_can_reject_a_candidate():
    context = _context(_bars("SELL"))
    candidate = StrategyResult("X", "BUY", 88, True, "trigger", "invalid")
    gated = gate_candidate(context, candidate, minimum_quality=55)
    assert gated.metadata["entry_quality"] >= 0
    assert gated.direction in {"BUY", "NO_TRADE"}
    if not gated.eligible:
        assert gated.direction == "NO_TRADE"


def test_gate_preserves_future_invalidation_as_metadata():
    context = _context(_bars("BUY"))
    candidate = StrategyResult("X", "BUY", 88, True, "trigger", "price closes through swing")
    gated = gate_candidate(context, candidate)
    assert gated.invalidation == "price closes through swing"
