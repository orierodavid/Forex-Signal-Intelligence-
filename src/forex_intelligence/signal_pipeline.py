from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping, Protocol
from uuid import uuid4

from forex_intelligence.anticipation import AnticipationEngine, AnticipationState
from forex_intelligence.domain import Direction, Evidence, MarketRegime, Signal, SignalStatus, Timeframe
from forex_intelligence.market_data import MarketSnapshot, MT5MarketDataProvider
from forex_intelligence.regime import RegimeEngine
from forex_intelligence.risk import PositionSize, RiskEngine, SymbolSpec
from forex_intelligence.strategy import StrategyContext, StrategySelector
from forex_intelligence.telegram import TelegramNotifier, signal_from_mapping


class SnapshotProvider(Protocol):
    def snapshot(self, symbol: str, timeframe: Timeframe, count: int = 300) -> MarketSnapshot: ...


MIN_EXECUTION_WINDOW_MINUTES = 30
FX_WEEKLY_OPEN_UTC_HOUR = 21
FX_WEEKLY_CLOSE_UTC_HOUR = 21
MIN_APPROVED_SCORE = 80.0
MIN_APPROVED_ENTRY_QUALITY = 65.0
TREND_REGIMES = {"STRONG_TREND_UP", "TREND_UP", "STRONG_TREND_DOWN", "TREND_DOWN"}


def _fx_market_is_open(now: datetime) -> bool:
    now = now.astimezone(timezone.utc)
    if now.weekday() == 5:
        return False
    if now.weekday() == 6:
        return now.hour >= FX_WEEKLY_OPEN_UTC_HOUR
    if now.weekday() == 4:
        return now.hour < FX_WEEKLY_CLOSE_UTC_HOUR
    return True


def _fx_minutes_until_close(now: datetime) -> float | None:
    now = now.astimezone(timezone.utc)
    if now.weekday() != 4:
        return None
    close = now.replace(hour=FX_WEEKLY_CLOSE_UTC_HOUR, minute=0, second=0, microsecond=0)
    return max(0.0, (close - now).total_seconds() / 60.0)


def _direction_regime(direction: str) -> set[str]:
    return {"STRONG_TREND_UP", "TREND_UP"} if direction == "BUY" else {"STRONG_TREND_DOWN", "TREND_DOWN"}


def _passes_approval_gate(candidate: object, context: StrategyContext) -> bool:
    score = float(getattr(candidate, "score", 0.0))
    metadata = getattr(candidate, "metadata", {}) or {}
    entry_quality = float(metadata.get("entry_quality", 0.0))
    direction = str(getattr(candidate, "direction", "NO_TRADE"))
    regime = context.regimes.get("M15", context.regime)
    if direction not in {"BUY", "SELL"} or score < MIN_APPROVED_SCORE or entry_quality < MIN_APPROVED_ENTRY_QUALITY:
        return False
    if regime not in TREND_REGIMES:
        return False
    aligned = _direction_regime(direction)
    return context.regimes.get("H1", "") in aligned and context.regimes.get("H4", "") in aligned


class SignalPipeline:
    """M15 primary; H1/H4 confirmation; validated strategy; mechanical entry trigger; risk sizing."""

    def __init__(self, provider: SnapshotProvider, *, regime_engine: RegimeEngine | None = None,
                 strategy_selector: StrategySelector | None = None,
                 anticipation_engine: AnticipationEngine | None = None,
                 risk_engine: RiskEngine | None = None, notifier: TelegramNotifier | None = None) -> None:
        self.provider = provider
        self.regime_engine = regime_engine or RegimeEngine()
        self.strategy_selector = strategy_selector or StrategySelector()
        self.anticipation_engine = anticipation_engine or AnticipationEngine()
        self.risk_engine = risk_engine or RiskEngine()
        self.notifier = notifier

    @staticmethod
    def _technical_levels(m15: MarketSnapshot, direction: str, current_price: float) -> tuple[float, float] | None:
        closed = m15.bars[:-1] if len(m15.bars) > 1 else m15.bars
        if len(closed) < 5:
            return None
        recent = closed[-5:]
        if direction == "BUY":
            stop = min(bar.low for bar in recent)
            distance = current_price - stop
            return (stop, current_price + distance * 2.0) if distance > 0 else None
        stop = max(bar.high for bar in recent)
        distance = stop - current_price
        return (stop, current_price - distance * 2.0) if distance > 0 else None

    def evaluate(self, *, pair: str, equity: float, symbol_spec: SymbolSpec,
                 trigger_confirmed: bool = False, now: datetime | None = None) -> tuple[Signal | None, PositionSize | None]:
        now = now or datetime.now(timezone.utc)
        if not _fx_market_is_open(now):
            return None, None
        minutes_to_close = _fx_minutes_until_close(now)
        if minutes_to_close is not None and minutes_to_close < MIN_EXECUTION_WINDOW_MINUTES:
            return None, None

        snapshots = {tf: self.provider.snapshot(pair, tf, 300) for tf in (Timeframe.H4, Timeframe.H1, Timeframe.M15)}
        if any(not snapshot.available or not snapshot.bars for snapshot in snapshots.values()):
            return None, None
        assessments = {tf: self.regime_engine.assess(snapshot) for tf, snapshot in snapshots.items()}
        m15 = snapshots[Timeframe.M15]
        m15_assessment = assessments[Timeframe.M15]
        if m15_assessment.regime == MarketRegime.UNTRADEABLE:
            return None, None
        context = StrategyContext(
            pair=pair, regime=m15_assessment.regime.value,
            bars={tf.value: snapshot.bars for tf, snapshot in snapshots.items()},
            current_price=m15.bars[-1].close,
            regimes={tf.value: assessment.regime.value for tf, assessment in assessments.items()},
        )
        candidate = self.strategy_selector.evaluate(context).selected
        if candidate is None or not _passes_approval_gate(candidate, context):
            return None, None

        setup = self.anticipation_engine.create_watch(setup_id=str(uuid4()), candidate=candidate, pair=pair,
                                                       current_price=context.current_price, now=now)
        if setup is None:
            return None, None
        # A READY setup means price is inside the strategy's explicit entry band.
        # That is the bot's mechanical trigger; external confirmation remains
        # available to callers but is not required for scheduled scanning.
        price_triggered = setup.potential_entry_low <= context.current_price <= setup.potential_entry_high
        setup = self.anticipation_engine.transition(
            setup, current_price=context.current_price,
            trigger_confirmed=trigger_confirmed or price_triggered, now=now,
        )
        if setup.state is not AnticipationState.TRIGGERED:
            return None, None

        levels = self._technical_levels(m15, setup.direction, context.current_price)
        if levels is None:
            return None, None
        stop_loss, take_profit = levels
        direction = Direction.BUY if setup.direction == "BUY" else Direction.SELL
        position = self.risk_engine.calculate_position_size(equity=equity, entry=context.current_price,
                                                             stop_loss=stop_loss, symbol=symbol_spec)
        signal = Signal(
            signal_id=uuid4(), pair=pair, direction=direction, strategy=setup.strategy,
            market_regime=m15_assessment.regime, current_price=context.current_price,
            entry=context.current_price, stop_loss=stop_loss, take_profit=take_profit,
            risk_reward=2.0, score=setup.score, confidence=min(100.0, m15_assessment.confidence),
            trigger=setup.trigger, invalidation=setup.invalidation, expiry=setup.expires_at,
            timeframes=(Timeframe.M15, Timeframe.H1, Timeframe.H4),
            evidence=tuple(Evidence(e, 1.0, 1.0, "analysis") for e in setup.evidence),
            timestamp=now, status=SignalStatus.TRIGGERED,
        )
        return signal, position

    def evaluate_and_notify(self, **kwargs: object) -> tuple[Signal | None, PositionSize | None]:
        signal, position = self.evaluate(**kwargs)
        if signal is not None and self.notifier is not None and position is not None:
            values: Mapping[str, object] = {
                "pair": signal.pair, "direction": signal.direction.value, "status": signal.status.value,
                "strategy": signal.strategy, "market_regime": signal.market_regime.value,
                "entry": f"{signal.entry:.8f}", "stop_loss": f"{signal.stop_loss:.8f}",
                "take_profit": f"{signal.take_profit:.8f}", "risk_reward": f"1:{signal.risk_reward:.2f}",
                "risk": f"0.5% | volume {position.volume:g} | max loss ${position.risk_amount:.2f}",
                "score": int(round(signal.score)), "confidence": f"{signal.confidence:.0f}%",
                "timeframes": "/".join(tf.value for tf in signal.timeframes),
                "evidence": "; ".join(e.name for e in signal.evidence), "trigger": signal.trigger,
                "invalidation": signal.invalidation, "expiry": signal.expiry.isoformat(),
            }
            self.notifier.send_signal(signal_from_mapping(values))
        return signal, position


def mt5_pipeline(terminal_path: str | None = None, *, notifier: TelegramNotifier | None = None) -> SignalPipeline:
    return SignalPipeline(MT5MarketDataProvider(terminal_path=terminal_path), notifier=notifier)
