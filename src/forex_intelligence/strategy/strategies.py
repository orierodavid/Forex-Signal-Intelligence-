from __future__ import annotations

from statistics import mean
from typing import Any, Sequence

from .base import StrategyContext, StrategyResult


def _value(bar: Any, key: str) -> float:
    if isinstance(bar, dict):
        return float(bar[key])
    return float(getattr(bar, key))


def _series(context: StrategyContext) -> list[Any]:
    bars = context.bars.get("M15") or context.bars.get("H1") or ()
    return list(bars)


def _ohlc(context: StrategyContext, minimum: int = 5) -> tuple[list[Any], bool]:
    bars = _series(context)
    return bars, len(bars) >= minimum


def _direction_from_closes(bars: Sequence[Any]) -> str:
    if len(bars) < 2:
        return "NO_TRADE"
    return "BUY" if _value(bars[-1], "close") > _value(bars[0], "close") else "SELL"


def _result(name: str, direction: str, score: float, eligible: bool, trigger: str, invalidation: str, *evidence: str) -> StrategyResult:
    return StrategyResult(
        strategy=name,
        direction=direction if eligible else "NO_TRADE",
        score=max(0.0, min(100.0, score)),
        eligible=eligible,
        trigger=trigger,
        invalidation=invalidation,
        evidence=tuple(evidence),
    )


class TrendPullbackStrategy:
    name = "TREND_PULLBACK"
    suitable_regimes = frozenset({"STRONG_TREND_UP", "TREND_UP", "STRONG_TREND_DOWN", "TREND_DOWN"})

    def evaluate(self, context: StrategyContext) -> StrategyResult:
        bars, ok = _ohlc(context, 20)
        if not ok or context.regime not in self.suitable_regimes:
            return _result(self.name, "NO_TRADE", 0, False, "trend/pullback evidence incomplete", "setup invalid")
        closes = [_value(b, "close") for b in bars[-20:]]
        direction = _direction_from_closes(closes and bars[-20:])
        recent = mean(closes[-3:])
        baseline = mean(closes[:10])
        aligned = (direction == "BUY" and recent >= baseline) or (direction == "SELL" and recent <= baseline)
        score = 72 + (8 if aligned else 0)
        return _result(self.name, direction, score, aligned, "M15 resumes in higher-timeframe direction", "M15 closes through the latest structural swing", "trend regime aligned", "pullback remains inside directional structure")


class BreakoutRetestStrategy:
    name = "BREAKOUT_RETEST"
    suitable_regimes = frozenset({"TREND_UP", "TREND_DOWN", "STRONG_TREND_UP", "STRONG_TREND_DOWN", "TRANSITION"})

    def evaluate(self, context: StrategyContext) -> StrategyResult:
        bars, ok = _ohlc(context, 25)
        if not ok or context.regime not in self.suitable_regimes:
            return _result(self.name, "NO_TRADE", 0, False, "breakout evidence incomplete", "setup invalid")
        prior = bars[-21:-5]
        recent = bars[-5:]
        prior_high = max(_value(b, "high") for b in prior)
        prior_low = min(_value(b, "low") for b in prior)
        close = _value(recent[-1], "close")
        if close > prior_high:
            return _result(self.name, "BUY", 88, True, f"M15 confirmation above {prior_high:.8f}", f"price closes back below {prior_high:.8f}", "range high broken", "close holds above breakout level")
        if close < prior_low:
            return _result(self.name, "SELL", 88, True, f"M15 confirmation below {prior_low:.8f}", f"price closes back above {prior_low:.8f}", "range low broken", "close holds below breakout level")
        return _result(self.name, "NO_TRADE", 54, False, "await clean breakout and retest", "breakout level fails", "compression/range identified")


class LiquiditySweepReversalStrategy:
    name = "LIQUIDITY_SWEEP_REVERSAL"
    suitable_regimes = frozenset({"RANGE", "TRANSITION", "HIGH_VOLATILITY"})

    def evaluate(self, context: StrategyContext) -> StrategyResult:
        bars, ok = _ohlc(context, 12)
        if not ok or context.regime not in self.suitable_regimes:
            return _result(self.name, "NO_TRADE", 0, False, "sweep evidence incomplete", "setup invalid")
        window = bars[-11:-1]
        high = max(_value(b, "high") for b in window)
        low = min(_value(b, "low") for b in window)
        last = bars[-1]
        close, high_last, low_last = _value(last, "close"), _value(last, "high"), _value(last, "low")
        if low_last < low and close > low:
            return _result(self.name, "BUY", 84, True, f"M15 closes back above swept low {low:.8f}", f"price accepts below {low:.8f}", "sell-side liquidity sweep", "reclaim confirmed")
        if high_last > high and close < high:
            return _result(self.name, "SELL", 84, True, f"M15 closes back below swept high {high:.8f}", f"price accepts above {high:.8f}", "buy-side liquidity sweep", "reclaim confirmed")
        return _result(self.name, "NO_TRADE", 48, False, "await liquidity sweep and reclaim", "sweep level fails")


class RangeBreakoutStrategy:
    name = "RANGE_BREAKOUT"
    suitable_regimes = frozenset({"RANGE", "TRANSITION", "LOW_VOLATILITY"})

    def evaluate(self, context: StrategyContext) -> StrategyResult:
        bars, ok = _ohlc(context, 30)
        if not ok or context.regime not in self.suitable_regimes:
            return _result(self.name, "NO_TRADE", 0, False, "range evidence incomplete", "setup invalid")
        window = bars[-25:-2]
        high = max(_value(b, "high") for b in window)
        low = min(_value(b, "low") for b in window)
        close = _value(bars[-1], "close")
        if close > high:
            return _result(self.name, "BUY", 82, True, f"close above range high {high:.8f}", f"close returns inside range below {high:.8f}", "defined consolidation range", "upside expansion")
        if close < low:
            return _result(self.name, "SELL", 82, True, f"close below range low {low:.8f}", f"close returns inside range above {low:.8f}", "defined consolidation range", "downside expansion")
        return _result(self.name, "NO_TRADE", 51, False, "await range expansion", "breakout fails")


class SupportResistanceRejectionStrategy:
    name = "SUPPORT_RESISTANCE_REJECTION"
    suitable_regimes = frozenset({"RANGE", "TRANSITION", "LOW_VOLATILITY"})

    def evaluate(self, context: StrategyContext) -> StrategyResult:
        bars, ok = _ohlc(context, 15)
        if not ok or context.regime not in self.suitable_regimes:
            return _result(self.name, "NO_TRADE", 0, False, "level evidence incomplete", "setup invalid")
        window = bars[-10:-1]
        resistance = max(_value(b, "high") for b in window)
        support = min(_value(b, "low") for b in window)
        last = bars[-1]
        close, high, low = _value(last, "close"), _value(last, "high"), _value(last, "low")
        if high >= resistance and close < resistance:
            return _result(self.name, "SELL", 79, True, f"rejection below resistance {resistance:.8f}", f"close above {resistance:.8f}", "resistance test", "rejection close")
        if low <= support and close > support:
            return _result(self.name, "BUY", 79, True, f"rejection above support {support:.8f}", f"close below {support:.8f}", "support test", "rejection close")
        return _result(self.name, "NO_TRADE", 50, False, "await level rejection", "level acceptance")


class MomentumContinuationStrategy:
    name = "MOMENTUM_CONTINUATION"
    suitable_regimes = frozenset({"STRONG_TREND_UP", "STRONG_TREND_DOWN", "HIGH_VOLATILITY", "TREND_UP", "TREND_DOWN"})

    def evaluate(self, context: StrategyContext) -> StrategyResult:
        bars, ok = _ohlc(context, 8)
        if not ok or context.regime not in self.suitable_regimes:
            return _result(self.name, "NO_TRADE", 0, False, "momentum evidence incomplete", "setup invalid")
        recent = bars[-5:]
        bodies = [_value(b, "close") - _value(b, "open") for b in recent]
        bullish = sum(1 for b in bodies if b > 0)
        bearish = sum(1 for b in bodies if b < 0)
        if bullish >= 4:
            return _result(self.name, "BUY", 81, True, "M15 closes with sustained bullish momentum", "momentum closes below recent impulse origin", "directional candle persistence")
        if bearish >= 4:
            return _result(self.name, "SELL", 81, True, "M15 closes with sustained bearish momentum", "momentum closes above recent impulse origin", "directional candle persistence")
        return _result(self.name, "NO_TRADE", 53, False, "await directional momentum", "momentum dissipates")


class MeanReversionStrategy:
    name = "MEAN_REVERSION"
    suitable_regimes = frozenset({"RANGE", "LOW_VOLATILITY"})

    def evaluate(self, context: StrategyContext) -> StrategyResult:
        bars, ok = _ohlc(context, 20)
        if not ok or context.regime not in self.suitable_regimes:
            return _result(self.name, "NO_TRADE", 0, False, "mean-reversion evidence incomplete", "setup invalid")
        closes = [_value(b, "close") for b in bars[-20:]]
        center = mean(closes)
        current = closes[-1]
        deviation = current - center
        if deviation > 0 and deviation / max(abs(center), 1e-12) > 0.001:
            return _result(self.name, "SELL", 74, True, "M15 confirms rejection from upper range deviation", "price accepts above the mean-reversion extreme", "range regime", "price extended from local mean")
        if deviation < 0 and abs(deviation) / max(abs(center), 1e-12) > 0.001:
            return _result(self.name, "BUY", 74, True, "M15 confirms rejection from lower range deviation", "price accepts below the mean-reversion extreme", "range regime", "price extended from local mean")
        return _result(self.name, "NO_TRADE", 47, False, "await meaningful deviation", "range structure breaks")


DEFAULT_STRATEGIES = (
    TrendPullbackStrategy(),
    BreakoutRetestStrategy(),
    LiquiditySweepReversalStrategy(),
    RangeBreakoutStrategy(),
    SupportResistanceRejectionStrategy(),
    MomentumContinuationStrategy(),
    MeanReversionStrategy(),
)
