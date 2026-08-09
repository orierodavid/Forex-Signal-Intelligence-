from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class EvidenceItem:
    name: str
    score: float
    weight: float
    passed: bool
    rationale: str

    @property
    def contribution(self) -> float:
        return self.score * self.weight


@dataclass(frozen=True)
class EvidenceAssessment:
    score: float
    passed: bool
    items: tuple[EvidenceItem, ...] = field(default_factory=tuple)
    reasons: tuple[str, ...] = field(default_factory=tuple)


class EvidenceEngine:
    """Deterministic evidence aggregation; never creates a direction by itself."""

    def __init__(self, minimum_score: float = 70.0) -> None:
        if not 0 <= minimum_score <= 100:
            raise ValueError("minimum_score must be between 0 and 100")
        self.minimum_score = minimum_score

    @staticmethod
    def _close(bar: Any) -> float:
        return float(bar["close"] if isinstance(bar, Mapping) else getattr(bar, "close"))

    @staticmethod
    def _open(bar: Any) -> float:
        return float(bar["open"] if isinstance(bar, Mapping) else getattr(bar, "open"))

    @staticmethod
    def _high(bar: Any) -> float:
        return float(bar["high"] if isinstance(bar, Mapping) else getattr(bar, "high"))

    @staticmethod
    def _low(bar: Any) -> float:
        return float(bar["low"] if isinstance(bar, Mapping) else getattr(bar, "low"))

    def assess(self, *, direction: str, regime: str, bars: Mapping[str, Sequence[Any]],
               strategy_evidence: Sequence[str] = ()) -> EvidenceAssessment:
        if direction not in {"BUY", "SELL"}:
            return EvidenceAssessment(0.0, False, reasons=("No directional candidate.",))

        items: list[EvidenceItem] = []
        regime_up = {"TREND_UP", "STRONG_TREND_UP"}
        regime_down = {"TREND_DOWN", "STRONG_TREND_DOWN"}
        if direction == "BUY":
            regime_pass = regime in regime_up
        else:
            regime_pass = regime in regime_down
        items.append(EvidenceItem("regime_alignment", 100.0 if regime_pass else 45.0, 0.25,
                                  regime_pass, f"Regime={regime}; directional alignment={regime_pass}."))

        tf_values: list[tuple[str, float]] = []
        for timeframe in ("H4", "H1", "M15"):
            series = list(bars.get(timeframe, ()))
            if len(series) >= 2:
                tf_values.append((timeframe, self._close(series[-1]) - self._close(series[0])))
        aligned = len(tf_values) == 3 and all((change > 0 if direction == "BUY" else change < 0) for _, change in tf_values)
        items.append(EvidenceItem("multi_timeframe_alignment", 100.0 if aligned else 40.0, 0.25,
                                  aligned, "H4/H1/M15 directional closes are aligned." if aligned else "Higher/lower timeframe alignment is incomplete."))

        m15 = list(bars.get("M15", ()))
        structure_pass = False
        structure_text = "M15 structure unavailable."
        if len(m15) >= 6:
            recent = m15[-5:]
            prior = m15[-6:-1]
            if direction == "BUY":
                structure_pass = self._close(recent[-1]) > max(self._high(b) for b in prior)
            else:
                structure_pass = self._close(recent[-1]) < min(self._low(b) for b in prior)
            structure_text = "M15 structure confirms directional expansion." if structure_pass else "M15 has no confirmed directional expansion."
        items.append(EvidenceItem("structure_confirmation", 100.0 if structure_pass else 50.0, 0.25,
                                  structure_pass, structure_text))

        momentum_pass = False
        momentum_text = "M15 momentum unavailable."
        if len(m15) >= 5:
            bodies = [self._close(b) - self._open(b) for b in m15[-5:]]
            if direction == "BUY":
                momentum_pass = sum(body > 0 for body in bodies) >= 3
            else:
                momentum_pass = sum(body < 0 for body in bodies) >= 3
            momentum_text = "Recent M15 candle bodies support direction." if momentum_pass else "Recent M15 candle bodies are mixed."
        items.append(EvidenceItem("momentum_confirmation", 100.0 if momentum_pass else 50.0, 0.15,
                                  momentum_pass, momentum_text))

        strategy_pass = bool(strategy_evidence)
        items.append(EvidenceItem("strategy_evidence", 100.0 if strategy_pass else 0.0, 0.10,
                                  strategy_pass, "Strategy supplied explicit evidence." if strategy_pass else "Strategy supplied no evidence."))

        score = round(sum(item.contribution for item in items), 2)
        passed = score >= self.minimum_score and all(item.passed for item in items[:2])
        reasons = tuple(item.rationale for item in items if not item.passed)
        return EvidenceAssessment(score, passed, tuple(items), reasons)
