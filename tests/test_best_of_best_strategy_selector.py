from forex_intelligence.strategy import StrategyContext, StrategySelector, StrategyResult


class Candidate:
    def __init__(self, name: str, result: StrategyResult):
        self.name = name
        self.suitable_regimes = frozenset()
        self._result = result

    def evaluate(self, context: StrategyContext) -> StrategyResult:
        return self._result


def context(regime_h4="TREND_UP", regime_h1="TREND_UP", regime_m15="TREND_UP"):
    return StrategyContext(
        pair="EURUSD",
        regime=regime_m15,
        bars={"H4": (), "H1": (), "M15": ()},
        current_price=1.1,
        regimes={"H4": regime_h4, "H1": regime_h1, "M15": regime_m15},
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


def test_scores_below_70_are_rejected_even_with_alignment():
    selector = StrategySelector((Candidate("SUPPORT_RESISTANCE", result("SUPPORT_RESISTANCE", "BUY", 69)),))
    assert selector.evaluate(context()).selected is None


def test_score_70_is_selected_for_early_telegram_alert():
    selector = StrategySelector((Candidate("SUPPORT_RESISTANCE", result("SUPPORT_RESISTANCE", "BUY", 70)),))
    selection = selector.evaluate(context("RANGE", "RANGE", "TREND_UP"))
    assert selection.selected is not None
    assert selection.selected.strategy == "SUPPORT_RESISTANCE"
    assert selection.selected.direction == "BUY"
    assert selection.selected.score == 70


def test_best_candidate_at_75_is_selected_and_alignment_ranks_it():
    selector = StrategySelector((Candidate("BREAKOUT_RETEST", result("BREAKOUT_RETEST", "BUY", 75)),))
    selection = selector.evaluate(context())
    assert selection.selected is not None
    assert selection.selected.strategy == "BREAKOUT_RETEST"
    assert selection.selected.score == 80


def test_close_opposing_candidates_are_rejected_in_neutral_m15_regime():
    selector = StrategySelector(
        (
            Candidate("BUY_SETUP", result("BUY_SETUP", "BUY", 86)),
            Candidate("SELL_SETUP", result("SELL_SETUP", "SELL", 83)),
        )
    )
    assert selector.evaluate(context(regime_m15="RANGE")).selected is None


def test_m15_direction_beats_higher_scoring_opposing_strategy():
    selector = StrategySelector(
        (
            Candidate("BUY_SETUP", result("BUY_SETUP", "BUY", 77)),
            Candidate("SELL_SETUP", result("SELL_SETUP", "SELL", 84)),
        )
    )
    selection = selector.evaluate(context("TREND_UP", "TREND_UP", "TREND_UP"))
    assert selection.selected is not None
    assert selection.selected.strategy == "BUY_SETUP"
    assert selection.selected.direction == "BUY"
    assert selection.selected.score == 82


def test_higher_timeframes_strengthen_m15_decision_without_replacing_it():
    selector = StrategySelector((Candidate("TREND_PULLBACK", result("TREND_PULLBACK", "BUY", 75)),))
    selection = selector.evaluate(context("TREND_UP", "TREND_UP", "TREND_UP"))
    assert selection.selected is not None
    assert selection.selected.strategy == "TREND_PULLBACK"
    assert selection.selected.score == 80


def test_higher_timeframes_do_not_flip_m15_direction():
    selector = StrategySelector(
        (
            Candidate("BUY_SETUP", result("BUY_SETUP", "BUY", 77)),
            Candidate("SELL_SETUP", result("SELL_SETUP", "SELL", 90)),
        )
    )
    selection = selector.evaluate(context("TREND_DOWN", "TREND_DOWN", "TREND_UP"))
    assert selection.selected is not None
    assert selection.selected.strategy == "BUY_SETUP"
    assert selection.selected.direction == "BUY"
