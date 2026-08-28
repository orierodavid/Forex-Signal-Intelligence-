from datetime import datetime, timezone
from types import SimpleNamespace

from forex_intelligence.signal_pipeline import _passes_approval_gate
from forex_intelligence.strategy import StrategyContext


def ctx(m15="TREND_UP", h1="TREND_UP", h4="TREND_UP"):
    return StrategyContext(
        pair="EURUSD",
        regime=m15,
        bars={"M15": (), "H1": (), "H4": ()},
        current_price=1.1,
        regimes={"M15": m15, "H1": h1, "H4": h4},
    )


def candidate(score=80, entry_quality=65, direction="BUY"):
    return SimpleNamespace(
        score=score,
        direction=direction,
        metadata={"entry_quality": entry_quality},
    )


def test_weak_scores_are_no_trade():
    assert not _passes_approval_gate(candidate(score=79), ctx())


def test_weak_entry_quality_is_no_trade():
    assert not _passes_approval_gate(candidate(entry_quality=64), ctx())


def test_trend_trade_requires_h1_and_h4_alignment():
    assert not _passes_approval_gate(candidate(), ctx(h1="RANGE", h4="TREND_UP"))
    assert not _passes_approval_gate(candidate(), ctx(h1="TREND_UP", h4="TREND_DOWN"))


def test_fully_aligned_trend_candidate_can_pass_final_gate():
    assert _passes_approval_gate(candidate(score=84, entry_quality=72), ctx())


def test_range_candidate_is_research_only_until_historical_evidence_is_wired():
    assert not _passes_approval_gate(candidate(score=95, entry_quality=90), ctx("RANGE", "RANGE", "RANGE"))
