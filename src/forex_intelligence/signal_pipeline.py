from __future__ import annotations

from dataclasses import replace
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


class SignalPipeline:
    """Runs the read-only analysis path and optionally emits a Telegram alert.

    Broker execution is deliberately absent. A caller must explicitly confirm
    the strategy trigger before a TRIGGERED signal can be emitted.
    """

    def __init__(
        self,
        provider: SnapshotProvider,
        *,
        regime_engine: RegimeEngine | None = None,
        strategy_selector: StrategySelector | None = None,
        anticipation_engine: AnticipationEngine | None = None,
        risk_engine: RiskEngine | None = None,
        notifier: TelegramNotifier | None = None,
    ) -> None:
        self.provider = provider
        self.regime_engine = regime_engine or RegimeEngine()
        self.strategy_selector = strategy_selector or StrategySelector()
        self.anticipation_engine = anticipation_engine or AnticipationEngine()
        self.risk_engine = risk_engine or RiskEngine()
        self.notifier = notifier

    def evaluate(
        self,
        *,
        pair: str,
        equity: float,
        symbol_spec: SymbolSpec,
        trigger_confirmed: bool = False,
        now: datetime | None = None,
    ) -> tuple[Signal | None, PositionSize | None]:
        now = now or datetime.now(timezone.utc)
        snapshots = {
            timeframe: self.provider.snapshot(pair, timeframe, 300)
            for timeframe in (Timeframe.H4, Timeframe.H1, Timeframe.M15)
        }
        assessments = {tf: self.regime_engine.assess(snapshot) for tf, snapshot in snapshots.items()}
        if any(assessment.regime == MarketRegime.UNTRADEABLE for assessment in assessments.values()):
            return None, None

        m15 = snapshots[Timeframe.M15]
        h1 = assessments[Timeframe.H1]
        if not m15.available or not m15.bars:
            return None, None

        current_price = m15.bars[-1].close
        context = StrategyContext(
            pair=pair,
            regime=h1.regime.value,
            bars={tf.value: snapshot.bars for tf, snapshot in snapshots.items()},
            current_price=current_price,
            regimes={tf.value: assessment.regime.value for tf, assessment in assessments.items()},
        )
        selection = self.strategy_selector.evaluate(context)
        candidate = selection.selected
        if candidate is None:
            return None, None

        setup = self.anticipation_engine.create_watch(
            setup_id=str(uuid4()),
            candidate=candidate,
            pair=pair,
            current_price=current_price,
            now=now,
        )
        if setup is None:
            return None, None
        setup = self.anticipation_engine.transition(
            setup,
            current_price=current_price,
            trigger_confirmed=trigger_confirmed,
            now=now,
        )
        if setup.state is not AnticipationState.TRIGGERED:
            return None, None

        closed_bars = m15.bars[:-1] if len(m15.bars) > 1 else m15.bars
        if len(closed_bars) < 5:
            return None, None
        recent = closed_bars[-5:]
        if setup.direction == "BUY":
            stop_loss = min(bar.low for bar in recent)
            stop_distance = current_price - stop_loss
            take_profit = current_price + stop_distance * 2.0
            direction = Direction.BUY
        else:
            stop_loss = max(bar.high for bar in recent)
            stop_distance = stop_loss - current_price
            take_profit = current_price - stop_distance * 2.0
            direction = Direction.SELL
        if stop_distance <= 0:
            return None, None

        position = self.risk_engine.calculate_position_size(
            equity=equity,
            entry=current_price,
            stop_loss=stop_loss,
            symbol=symbol_spec,
        )
        signal = Signal(
            signal_id=uuid4(),
            pair=pair,
            direction=direction,
            strategy=setup.strategy,
            market_regime=h1.regime,
            current_price=current_price,
            entry=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward=2.0,
            score=setup.score,
            confidence=min(100.0, h1.confidence),
            trigger=setup.trigger,
            invalidation=setup.invalidation,
            expiry=setup.expires_at,
            timeframes=(Timeframe.H4, Timeframe.H1, Timeframe.M15),
            evidence=tuple(Evidence(e, 1.0, 1.0, "analysis") for e in setup.evidence),
            timestamp=now,
            status=SignalStatus.TRIGGERED,
        )
        return signal, position

    def evaluate_and_notify(self, **kwargs: object) -> tuple[Signal | None, PositionSize | None]:
        signal, position = self.evaluate(**kwargs)
        if signal is not None and self.notifier is not None and position is not None:
            values: Mapping[str, object] = {
                "pair": signal.pair,
                "direction": signal.direction.value,
                "status": signal.status.value,
                "strategy": signal.strategy,
                "market_regime": signal.market_regime.value,
                "entry": f"{signal.entry:.8f}",
                "stop_loss": f"{signal.stop_loss:.8f}",
                "take_profit": f"{signal.take_profit:.8f}",
                "risk_reward": f"1:{signal.risk_reward:.2f}",
                "risk": f"0.5% | volume {position.volume:g}",
                "score": int(round(signal.score)),
                "confidence": f"{signal.confidence:.0f}%",
                "timeframes": "/".join(tf.value for tf in signal.timeframes),
                "evidence": "; ".join(e.name for e in signal.evidence),
                "trigger": signal.trigger,
                "invalidation": signal.invalidation,
                "expiry": signal.expiry.isoformat(),
            }
            self.notifier.send_signal(signal_from_mapping(values))
        return signal, position


def mt5_pipeline(
    terminal_path: str | None = None,
    *,
    notifier: TelegramNotifier | None = None,
) -> SignalPipeline:
    """Construct the production pipeline around the read-only MT5 adapter."""
    return SignalPipeline(MT5MarketDataProvider(terminal_path=terminal_path), notifier=notifier)
