from __future__ import annotations

from math import isfinite
from statistics import mean
from typing import Any, Sequence

from .base import StrategyContext, StrategyResult


def _v(bar: Any, key: str) -> float:
    return float(bar[key] if isinstance(bar, dict) else getattr(bar, key))


def entry_quality(context: StrategyContext, candidate: StrategyResult) -> float:
    """Score whether the M15 entry is timely rather than merely directional.

    This is deliberately independent of the strategy's raw score. It penalizes
    chasing extended candles and rewards a decisive confirmation candle that is
    still close to the recent structural area. It is a setup-quality filter, not
    an outcome prediction.
    """
    bars: Sequence[Any] = context.bars.get("M15") or ()
    if len(bars) < 12 or candidate.direction not in {"BUY", "SELL"}:
        return 0.0

    recent = bars[-12:]
    last = recent[-1]
    high = _v(last, "high")
    low = _v(last, "low")
    close = _v(last, "close")
    open_ = _v(last, "open")
    candle_range = high - low
    if candle_range <= 0:
        return 0.0

    body = abs(close - open_)
    body_ratio = min(1.0, body / candle_range)
    directional = close > open_ if candidate.direction == "BUY" else close < open_
    confirmation = 25.0 if directional else 0.0
    body_component = 25.0 * body_ratio

    prior = recent[:-1]
    prior_high = max(_v(b, "high") for b in prior)
    prior_low = min(_v(b, "low") for b in prior)
    span = prior_high - prior_low
    if span <= 0:
        return min(100.0, confirmation + body_component)

    # Avoid entering after a candle has already consumed almost the entire
    # recent range. Such entries often have poor room to the structural stop.
    if candidate.direction == "BUY":
        location = (close - prior_low) / span
        location_quality = max(0.0, 1.0 - max(0.0, location - 0.70) / 0.30)
    else:
        location = (prior_high - close) / span
        location_quality = max(0.0, 1.0 - max(0.0, location - 0.70) / 0.30)
    location_component = 30.0 * location_quality

    closes = [_v(b, "close") for b in recent]
    drift = closes[-1] - mean(closes[:-1])
    drift_ratio = abs(drift) / max(span, 1e-12)
    chase_penalty = min(20.0, max(0.0, drift_ratio - 0.35) * 40.0)

    score = confirmation + body_component + location_component - chase_penalty
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
