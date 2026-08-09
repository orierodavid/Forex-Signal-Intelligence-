from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace

from forex_intelligence.evidence import EvidenceAssessment, EvidenceEngine

from .base import StrategyContext, StrategyResult
from .selector import StrategySelector


@dataclass(frozen=True)
class EvidenceSelection:
    selected: StrategyResult | None
    candidates: tuple[StrategyResult, ...]
    evidence: tuple[tuple[str, EvidenceAssessment], ...]
    threshold: float

    @property
    def direction(self) -> str:
        return self.selected.direction if self.selected else "NO_TRADE"


class EvidenceAwareStrategySelector:
    """Selects only candidates that clear both strategy and independent evidence gates."""

    def __init__(self, strategy_selector: StrategySelector | None = None,
                 evidence_engine: EvidenceEngine | None = None,
                 minimum_score: float = 70.0) -> None:
        self.strategy_selector = strategy_selector or StrategySelector(minimum_score=minimum_score)
        self.evidence_engine = evidence_engine or EvidenceEngine(minimum_score=minimum_score)
        self.minimum_score = minimum_score

    def evaluate(self, context: StrategyContext) -> EvidenceSelection:
        base = self.strategy_selector.evaluate(context)
        assessments: list[tuple[str, EvidenceAssessment]] = []
        qualified: list[StrategyResult] = []

        for candidate in base.candidates:
            if not candidate.eligible or candidate.direction == "NO_TRADE":
                continue
            assessment = self.evidence_engine.assess(
                direction=candidate.direction,
                regime=context.regime,
                bars=context.bars,
                strategy_evidence=candidate.evidence,
            )
            assessments.append((candidate.strategy, assessment))
            combined = round(candidate.score * 0.65 + assessment.score * 0.35, 2)
            if assessment.passed and combined >= self.minimum_score:
                qualified.append(replace(candidate, score=combined))

        qualified.sort(key=lambda item: (-item.score, item.strategy))
        if not qualified:
            return EvidenceSelection(None, base.candidates, tuple(assessments), self.minimum_score)

        winner = qualified[0]
        opposing = [candidate for candidate in qualified[1:] if candidate.direction != winner.direction]
        if opposing and winner.score - opposing[0].score < 5.0:
            return EvidenceSelection(None, base.candidates, tuple(assessments), self.minimum_score)
        return EvidenceSelection(winner, base.candidates, tuple(assessments), self.minimum_score)
