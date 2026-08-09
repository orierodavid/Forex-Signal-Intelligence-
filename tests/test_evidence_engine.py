from forex_intelligence.evidence import EvidenceEngine


def bar(open_, high, low, close):
    return {"open": open_, "high": high, "low": low, "close": close}


def aligned_bars():
    return {
        "H4": [bar(1, 1.1, .9, 1.2), bar(1.2, 1.3, 1.1, 1.4)],
        "H1": [bar(1, 1.1, .9, 1.15), bar(1.15, 1.3, 1.1, 1.35)],
        "M15": [
            bar(1, 1.02, .99, 1.01), bar(1.01, 1.03, 1, 1.02),
            bar(1.02, 1.04, 1.01, 1.03), bar(1.03, 1.05, 1.02, 1.04),
            bar(1.04, 1.06, 1.03, 1.05), bar(1.05, 1.10, 1.04, 1.09),
        ],
    }


def test_aligned_buy_evidence_passes():
    assessment = EvidenceEngine().assess(
        direction="BUY", regime="TREND_UP", bars=aligned_bars(), strategy_evidence=("trend",)
    )
    assert assessment.passed
    assert assessment.score >= 70


def test_missing_higher_timeframe_alignment_blocks_pass():
    bars = aligned_bars()
    bars["H4"] = [bar(1.2, 1.25, 1.0, 1.1), bar(1.1, 1.15, .95, 1.0)]
    assessment = EvidenceEngine().assess(
        direction="BUY", regime="TREND_UP", bars=bars, strategy_evidence=("trend",)
    )
    assert not assessment.passed


def test_no_direction_is_no_trade():
    assessment = EvidenceEngine().assess(direction="NO_TRADE", regime="TREND_UP", bars=aligned_bars())
    assert not assessment.passed
    assert assessment.score == 0


def test_strategy_evidence_is_explicit():
    assessment = EvidenceEngine().assess(
        direction="BUY", regime="TREND_UP", bars=aligned_bars(), strategy_evidence=()
    )
    assert any(item.name == "strategy_evidence" and not item.passed for item in assessment.items)
