from __future__ import annotations

from forex_intelligence.domain import MarketRegime, Timeframe
from forex_intelligence.market_data import MarketSnapshot
from forex_intelligence.regime.indicators import adx, atr, ema, linear_slope, stdev
from forex_intelligence.regime.models import RegimeAssessment, RegimeMetrics


class RegimeEngine:
    """Deterministic multi-factor market-regime classifier.

    It intentionally uses closed-bar data supplied by the snapshot. The current
    forming MT5 bar is excluded so regime decisions cannot accidentally depend
    on intrabar values that will later disappear.
    """

    def __init__(self, ema_fast_period: int = 20, ema_slow_period: int = 50, atr_period: int = 14) -> None:
        if ema_fast_period >= ema_slow_period:
            raise ValueError("fast EMA period must be smaller than slow EMA period")
        self.ema_fast_period = ema_fast_period
        self.ema_slow_period = ema_slow_period
        self.atr_period = atr_period

    def assess(self, snapshot: MarketSnapshot) -> RegimeAssessment:
        if not snapshot.available:
            return RegimeAssessment(
                snapshot.symbol, snapshot.timeframe, MarketRegime.UNTRADEABLE, 100.0,
                RegimeMetrics(0, 0, 0, 0, 0, 0, 0), ("market data unavailable",),
            )
        bars = list(snapshot.bars[:-1])  # exclude still-forming bar
        minimum = max(self.ema_slow_period + 5, self.atr_period * 2 + 1, 40)
        if len(bars) < minimum:
            return RegimeAssessment(
                snapshot.symbol, snapshot.timeframe, MarketRegime.UNTRADEABLE, 100.0,
                RegimeMetrics(0, 0, 0, 0, 0, 0, 0), (f"insufficient closed bars: {len(bars)}/{minimum}",),
            )

        closes = [b.close for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]
        fast = ema(closes, self.ema_fast_period)
        slow = ema(closes, self.ema_slow_period)
        current = closes[-1]
        current_atr = atr(highs, lows, closes, self.atr_period)
        current_adx = adx(highs, lows, closes, self.atr_period)
        slope = linear_slope(closes[-20:])
        atr_percent = current_atr / current if current else 0.0
        recent_range = max(highs[-20:]) - min(lows[-20:])
        compression_ratio = stdev(closes[-20:]) / current_atr if current_atr else 0.0
        directional = (fast - slow) / current_atr if current_atr else 0.0
        slope_normalized = slope * 20 / current_atr if current_atr else 0.0

        reasons: list[str] = []
        if current_adx >= 30:
            trend_strength = "strong"
        elif current_adx >= 20:
            trend_strength = "moderate"
        else:
            trend_strength = "weak"

        if current_adx >= 25 and directional >= 0.75 and slope_normalized > 0.15:
            regime = MarketRegime.STRONG_TREND_UP
            reasons.extend(("ADX confirms directional strength", "fast EMA is materially above slow EMA", "price slope is positive"))
        elif current_adx >= 20 and directional >= 0.25 and slope_normalized > 0:
            regime = MarketRegime.TREND_UP
            reasons.extend(("moderate trend strength", "bullish EMA separation", "positive price slope"))
        elif current_adx >= 25 and directional <= -0.75 and slope_normalized < -0.15:
            regime = MarketRegime.STRONG_TREND_DOWN
            reasons.extend(("ADX confirms directional strength", "fast EMA is materially below slow EMA", "price slope is negative"))
        elif current_adx >= 20 and directional <= -0.25 and slope_normalized < 0:
            regime = MarketRegime.TREND_DOWN
            reasons.extend(("moderate trend strength", "bearish EMA separation", "negative price slope"))
        elif atr_percent >= 0.01 and current_adx >= 25:
            regime = MarketRegime.HIGH_VOLATILITY
            reasons.extend(("ATR is elevated relative to price", "ADX confirms active directional movement"))
        elif compression_ratio < 0.75 and current_adx < 18:
            regime = MarketRegime.LOW_VOLATILITY
            reasons.extend(("price dispersion is compressed relative to ATR", "ADX is weak"))
        elif current_adx < 18 and recent_range <= current_atr * 5:
            regime = MarketRegime.RANGE
            reasons.extend(("ADX is weak", "recent range is bounded by volatility"))
        elif current_adx < 22:
            regime = MarketRegime.TRANSITION
            reasons.append("trend strength is insufficient for directional classification")
        else:
            regime = MarketRegime.TRANSITION
            reasons.append("factors are not sufficiently aligned")

        confidence = min(100.0, max(0.0, 50 + abs(directional) * 20 + max(0, current_adx - 15) * 1.2))
        metrics = RegimeMetrics(fast, slow, current_atr, atr_percent, current_adx, directional, compression_ratio)
        reasons.append(f"{trend_strength} trend-strength classification")
        return RegimeAssessment(snapshot.symbol, snapshot.timeframe, regime, round(confidence, 2), metrics, tuple(reasons))
