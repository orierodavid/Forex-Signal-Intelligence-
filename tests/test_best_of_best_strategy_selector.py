from forex_intelligence.strategy import StrategyContext, StrategySelector, StrategyResult


class Candidate:
    def __init__(self, name: str, result: StrategyResult):
        self.name = name
        self.suitable_regimes = frozenset()
        self._result = result

    def evaluate(self, context: StrategyContext) -> StrategyResult:
        return self._result


def context(regime_h4="TREND_UP", regime_h1="TREND_UP"):
    return StrategyContext(
        pair="EURUSD",
        regime=regime_h1,
        bars={"H4": (), "H1": (), "M15": ()},
        current_price=1.1,
        regimes={"H4": regime_h4, "H1": regime_h1, "M15": regime_h1},
    )


def result(name, direction, score):
    return StrategyResult(
        strategy=name,
        direction=direction,
        score=score,
        eligible=True,
        trigger="confirmed",
        invalidation="invalidated",
    )


def test_scores_below_80_are_rejected_even_with_alignment():
    selector = StrategySelector((Candidate("SUPPORT_RESISTANCE", result("SUPPORT_RESISTANCE", "BUY", 79)),))
    assert selector.evaluate(context()).selected is None


def test_best_candidate_at_80_is_selected_and_alignment_ranks_it():
    selector = StrategySelector((Candidate("BREAKOUT_RETEST", result("BREAKOUT_RETEST", "BUY", 80)),))
    selection = selector.evaluate(context())
    assert selection.selected is not None
    assert selection.selected.strategy == "BREAKOUT_RETEST"
    assert selection.selected.score == 85


def test_close_opposing_candidates_are_rejected():
    selector = StrategySelector(
        (
            Candidate("BUY_SETUP", result("BUY_SETUP", "BUY", 86)),
            Candidate("SELL_SETUP", result("SELL_SETUP", "SELL", 83)),
        )
    )
    assert selector.evaluate(context()).selected is None


def test_higher_timeframe_alignment_ranks_a_qualified_candidate():
    selector = StrategySelector((Candidate("TREND_PULLBACK", result("TREND_PULLBACK", "BUY", 80)),))
    selection = selector.evaluate(context("TREND_UP", "TREND_UP"))
    assert selection.selected is not None
    assert selection.selected.strategy == "TREND_PULLBACK"
    assert selection.selected.score == 85
