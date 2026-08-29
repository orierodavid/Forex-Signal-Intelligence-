from forex_intelligence.strategy import StrategyContext, StrategyProfile, StrategySelector, StrategyResult


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
    return StrategyResult(strategy=name, direction=direction, score=score, eligible=True, trigger="confirmed", invalidation="invalidated")


def selector(candidates, assignments):
    return StrategySelector(candidates, profile=StrategyProfile(assignments))


def test_scores_below_70_are_rejected_even_with_alignment():
    candidate = Candidate("SUPPORT_RESISTANCE", result("SUPPORT_RESISTANCE", "BUY", 69))
    assert selector((candidate,), {"EURUSD|TREND_UP": "SUPPORT_RESISTANCE"}).evaluate(context()).selected is None


def test_score_70_is_selected_for_early_telegram_alert():
    candidate = Candidate("SUPPORT_RESISTANCE", result("SUPPORT_RESISTANCE", "BUY", 70))
    selection = selector((candidate,), {"EURUSD|TREND_UP": "SUPPORT_RESISTANCE", "EURUSD|RANGE": "SUPPORT_RESISTANCE"}).evaluate(context("RANGE", "RANGE", "TREND_UP"))
    assert selection.selected is not None
    assert selection.selected.strategy == "SUPPORT_RESISTANCE"
    assert selection.selected.direction == "BUY"
    assert selection.selected.score == 70


def test_best_candidate_at_75_is_selected_and_alignment_ranks_it():
    candidate = Candidate("BREAKOUT_RETEST", result("BREAKOUT_RETEST", "BUY", 75))
    selection = selector((candidate,), {"EURUSD|TREND_UP": "BREAKOUT_RETEST"}).evaluate(context())
    assert selection.selected is not None
    assert selection.selected.strategy == "BREAKOUT_RETEST"
    assert selection.selected.score == 80


def test_close_opposing_candidates_are_rejected_in_neutral_m15_regime():
    selection = selector((Candidate("BUY_SETUP", result("BUY_SETUP", "BUY", 86)), Candidate("SELL_SETUP", result("SELL_SETUP", "SELL", 83))), {}).evaluate(context(regime_m15="RANGE"))
    assert selection.selected is None


def test_m15_direction_beats_higher_scoring_opposing_strategy():
    selection = selector((Candidate("BUY_SETUP", result("BUY_SETUP", "BUY", 77)), Candidate("SELL_SETUP", result("SELL_SETUP", "SELL", 84))), {"EURUSD|TREND_UP": "BUY_SETUP"}).evaluate(context())
    assert selection.selected is not None
    assert selection.selected.strategy == "BUY_SETUP"
    assert selection.selected.direction == "BUY"
    assert selection.selected.score == 82


def test_higher_timeframes_strengthen_m15_decision_without_replacing_it():
    candidate = Candidate("TREND_PULLBACK", result("TREND_PULLBACK", "BUY", 75))
    selection = selector((candidate,), {"EURUSD|TREND_UP": "TREND_PULLBACK"}).evaluate(context())
    assert selection.selected is not None
    assert selection.selected.strategy == "TREND_PULLBACK"
    assert selection.selected.score == 80


def test_higher_timeframes_do_not_flip_m15_direction():
    selection = selector((Candidate("BUY_SETUP", result("BUY_SETUP", "BUY", 77)), Candidate("SELL_SETUP", result("SELL_SETUP", "SELL", 90))), {"EURUSD|TREND_UP": "BUY_SETUP"}).evaluate(context("TREND_DOWN", "TREND_DOWN", "TREND_UP"))
    assert selection.selected is not None
    assert selection.selected.strategy == "BUY_SETUP"
    assert selection.selected.direction == "BUY"
