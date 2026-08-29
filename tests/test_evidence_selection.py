from forex_intelligence.strategy import StrategyContext, StrategyProfile, EvidenceAwareStrategySelector, StrategySelector


def bar(open_, high, low, close):
    return {"open": open_, "high": high, "low": low, "close": close}


def trend_bars():
    h4 = [bar(1 + i * .01, 1.011 + i * .01, .999 + i * .01, 1.009 + i * .01) for i in range(8)]
    h1 = [bar(1 + i * .003, 1.004 + i * .003, .999 + i * .003, 1.003 + i * .003) for i in range(12)]
    m15 = [bar(1 + i * .001, 1.0015 + i * .001, .9995 + i * .001, 1.001 + i * .001) for i in range(24)]
    return {"H4": h4, "H1": h1, "M15": m15}


def test_evidence_selector_preserves_no_trade_when_evidence_is_insufficient():
    context = StrategyContext("EURUSD", "TREND_UP", {"M15": trend_bars()["M15"]}, 1.024)
    result = EvidenceAwareStrategySelector().evaluate(context)
    assert result.direction == "NO_TRADE"
    assert result.selected is None


def test_evidence_selector_records_assessments_for_candidates():
    context = StrategyContext("EURUSD", "TREND_UP", trend_bars(), 1.024)
    selector = StrategySelector(profile=StrategyProfile({"EURUSD|TREND_UP": "TREND_PULLBACK"}))
    result = EvidenceAwareStrategySelector(strategy_selector=selector).evaluate(context)
    assert result.evidence
    names = {name for name, _ in result.evidence}
    assert "TREND_PULLBACK" in names
