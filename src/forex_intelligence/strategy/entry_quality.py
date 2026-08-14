from __future__ import annotations

from math import isfinite
from statistics import mean
from typing import Any, Sequence

from .base import StrategyContext, StrategyResult


def _v(bar: Any, key: str) -> float:
    return float(bar[key] if isinstance(bar, dict) else getattr(bar, key))


def entry_quality(context: StrategyContext, candidate: StrategyResult) -> float:
    """Score whether an M15 entry is timely and sufficiently supported."""
    bars: Sequence[Any] = context.bars.get("M15") or ()
    if len(bars) < 12 or candidate.direction not in {"BUY", "SELL"}:
        return 0.0
    recent = bars[-12:]
    last = recent[-1]
    high, low = _v(last, "high"), _v(last, "low")
    close, open_ = _v(last, "close"), _v(last, "open")
    candle_range = high - low
    if candle_range <= 0:
        return 0.0
    body_ratio = min(1.0, abs(close - open_) / candle_range)
    directional = close > open_ if candidate.direction == "BUY" else close < open_
    confirmation = 25.0 if directional else 0.0
    body_component = 25.0 * body_ratio
    prior = recent[:-1]
    prior_high = max(_v(b, "high") for b in prior)
    prior_low = min(_v(b, "low") for b in prior)
    span = prior_high - prior_low
    if span <= 0:
        return min(100.0, confirmation + body_component)
    location = ((close - prior_low) / span) if candidate.direction == "BUY" else ((prior_high - close) / span)
    location_quality = max(0.0, 1.0 - max(0.0, location - 0.70) / 0.30)

    bullish = {"TREND_UP", "STRONG_TREND_UP"}
    bearish = {"TREND_DOWN", "STRONG_TREND_DOWN"}
    aligned = bullish if candidate.direction == "BUY" else bearish
    m15_aligned = context.regimes.get("M15", context.regime) in aligned
    h1_aligned = context.regimes.get("H1", "") in aligned
    h4_aligned = context.regimes.get("H4", "") in aligned
    if m15_aligned:
        location_quality = max(location_quality, 0.35)
    if h1_aligned:
        location_quality = max(location_quality, 0.25)
    if h4_aligned:
        location_quality = max(location_quality, 0.20)
    location_component = 30.0 * location_quality

    closes = [_v(b, "close") for b in recent]
    drift = closes[-1] - mean(closes[:-1])
    drift_ratio = abs(drift) / max(span, 1e-12)
    chase_penalty = min(20.0, max(0.0, drift_ratio - 0.55) * 30.0)
    confluence_bonus = 10.0 * m15_aligned + 5.0 * h1_aligned + 5.0 * h4_aligned
    score = confirmation + body_component + location_component + confluence_bonus - chase_penalty
    return max(0.0, min(100.0, score)) if isfinite(score) else 0.0


def gate_candidate(context: StrategyContext, candidate: StrategyResult, minimum_quality: float = 55.0) -> StrategyResult:
    quality = entry_quality(context, candidate)
    metadata = dict(candidate.metadata)
    metadata["entry_quality"] = quality
    metadata["raw_score"] = candidate.score
    if not candidate.eligible or quality < minimum_quality:
        return StrategyResult(
            strategy=candidate.strategy,
            direction="NO_TRADE",
            score=quality,
            eligible=False,
            trigger=candidate.trigger,
            invalidation=candidate.invalidation,
            evidence=candidate.evidence + (f"entry quality {quality:.1f}/{minimum_quality:.1f}",),
            metadata=metadata,
        )
    adjusted = min(100.0, 0.65 * candidate.score + 0.35 * quality)
    return StrategyResult(
        strategy=candidate.strategy,
        direction=candidate.direction,
        score=adjusted,
        eligible=True,
        trigger=candidate.trigger,
        invalidation=candidate.invalidation,
        evidence=candidate.evidence + (f"entry quality {quality:.1f}/{minimum_quality:.1f}",),
        metadata=metadata,
    )
