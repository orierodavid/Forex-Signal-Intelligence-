from datetime import datetime, timedelta, timezone

from forex_intelligence.anticipation import AnticipationEngine, AnticipationState
from forex_intelligence.strategy.base import StrategyResult


def candidate(**metadata):
    return StrategyResult(
        strategy="Trend Pullback",
        direction="BUY",
        score=86,
        eligible=True,
        trigger="M15 confirmation above entry zone",
        invalidation="M15 close below structure",
        evidence=("H4 bullish", "H1 bullish", "M15 pullback"),
        metadata=metadata,
    )


def test_create_watch_is_watching_outside_entry_zone():
    now = datetime(2026, 8, 9, tzinfo=timezone.utc)
    setup = AnticipationEngine(60).create_watch(
        setup_id="s1", candidate=candidate(entry_low=100, entry_high=101),
        pair="EURUSD", current_price=99, now=now,
    )
    assert setup.state is AnticipationState.WATCHING
    assert setup.expires_at == now + timedelta(minutes=60)


def test_create_watch_becomes_ready_inside_entry_zone():
    now = datetime(2026, 8, 9, tzinfo=timezone.utc)
    setup = AnticipationEngine().create_watch(
        setup_id="s2", candidate=candidate(entry_low=100, entry_high=101),
        pair="EURUSD", current_price=100.5, now=now,
    )
    assert setup.state is AnticipationState.READY


def test_transition_requires_explicit_trigger():
    now = datetime(2026, 8, 9, tzinfo=timezone.utc)
    engine = AnticipationEngine()
    setup = engine.create_watch(
        setup_id="s3", candidate=candidate(entry_low=100, entry_high=101),
        pair="EURUSD", current_price=100.5, now=now,
    )
    # Keep the transition timestamp deterministic and before expiry.
    transition_time = now + timedelta(minutes=30)
    updated = engine.transition(
        setup, current_price=100.7, trigger_confirmed=False, now=transition_time,
    )
    assert updated.state is AnticipationState.READY
    triggered = engine.transition(
        setup, current_price=100.7, trigger_confirmed=True, now=transition_time,
    )
    assert triggered.state is AnticipationState.TRIGGERED


def test_invalidation_wins_over_trigger():
    now = datetime(2026, 8, 9, tzinfo=timezone.utc)
    setup = AnticipationEngine().create_watch(
        setup_id="s4", candidate=candidate(entry_low=100, entry_high=101),
        pair="EURUSD", current_price=100.5, now=now,
    )
    updated = AnticipationEngine().transition(
        setup, current_price=99, trigger_confirmed=True, invalidated=True, now=now,
    )
    assert updated.state is AnticipationState.INVALIDATED


def test_expiry_is_terminal():
    now = datetime(2026, 8, 9, tzinfo=timezone.utc)
    setup = AnticipationEngine(60).create_watch(
        setup_id="s5", candidate=candidate(entry_low=100, entry_high=101),
        pair="EURUSD", current_price=99, now=now,
    )
    expired = AnticipationEngine().transition(
        setup, current_price=99, trigger_confirmed=False, now=setup.expires_at,
    )
    assert expired.state is AnticipationState.EXPIRED


def test_no_trade_candidate_is_not_anticipated():
    candidate_no_trade = StrategyResult(
        strategy="Mean Reversion", direction="NO_TRADE", score=30, eligible=False,
        trigger="", invalidation="",
    )
    setup = AnticipationEngine().create_watch(
        setup_id="s6", candidate=candidate_no_trade, pair="EURUSD", current_price=100,
    )
    assert setup is None
