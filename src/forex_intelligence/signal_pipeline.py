from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


def _fx_market_is_open(now: datetime) -> bool:
    """Conservative weekly FX session gate in UTC.

    The broker remains the final execution authority. This gate prevents the
    Telegram signal path from producing actionable alerts during the normal
    weekend closure and during the final execution-window cutoff on Friday.
    """
    now = now.astimezone(timezone.utc)
    weekday = now.weekday()  # Monday=0 ... Friday=4, Saturday=5, Sunday=6
    hour = now.hour + now.minute / 60 + now.second / 3600

    if weekday == 5:  # Saturday
        return False
    if weekday == 6:  # Sunday, before the weekly open
        return hour >= FX_WEEKLY_OPEN_UTC_HOUR
    if weekday == 4:  # Friday, stop sending before the weekly close
        return hour < FX_WEEKLY_CLOSE_UTC_HOUR - MIN_EXECUTION_WINDOW_MINUTES / 60
    return True


def _fx_minutes_until_close(now: datetime) -> float | None:
    """Return minutes until the conservative Friday weekly close."""
    now = now.astimezone(timezone.utc)
    if now.weekday() != 4:
        return None
    close = now.replace(hour=FX_WEEKLY_CLOSE_UTC_HOUR, minute=0, second=0, microsecond=0)
    return max(0.0, (close - now).total_seconds() / 60.0)


class SignalPipeline:
    """Runs the read-only analysis path and optionally emits a Telegram alert.

    M15 is the primary trading timeframe. H1 and H4 are higher-timeframe
    confirmation layers used to strengthen or weaken the M15 decision.

    Scores 70-74 are early Telegram alerts only: they deliberately bypass risk
    sizing/vetting but still receive complete technical entry, stop-loss and
    take-profit levels. The alert title/status is RISK_NOT_VETTED. Scores 75+
    continue through the normal trigger and risk-sizing gates.
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

    @staticmethod
    def _technical_levels(m15: MarketSnapshot, direction: str, current_price: float) -> tuple[float, float] | None:
        closed_bars = m15.bars[:-1] if len(m15.bars) > 1 else m15.bars
        if len(closed_bars) < 5:
            return None
        recent = closed_bars[-5:]
        if direction == "BUY":
            stop_loss = min(bar.low for bar in recent)
            stop_distance = current_price - stop_loss
            if stop_distance <= 0:
                return None
            take_profit = current_price + stop_distance * 2.0
        else:
            stop_loss = max(bar.high for bar in recent)
            stop_distance = stop_loss - current_price
            if stop_distance <= 0:
                return None
            take_profit = current_price - stop_distance * 2.0
        return stop_loss, take_profit

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

        # Never emit actionable Telegram signals while the normal weekly FX
        # market is closed or too close to the Friday close to provide the
        # minimum execution window. The broker remains the final authority.
        if not _fx_market_is_open(now):
            return None, None
        minutes_to_close = _fx_minutes_until_close(now)
        if minutes_to_close is not None and minutes_to_close < MIN_EXECUTION_WINDOW_MINUTES:
            return None, None

        snapshots = {
            timeframe: self.provider.snapshot(pair, timeframe, 300)
            for timeframe in (Timeframe.H4, Timeframe.H1, Timeframe.M15)
        }
        assessments = {tf: self.regime_engine.assess(snapshot) for tf, snapshot in snapshots.items()}

        m15 = snapshots[Timeframe.M15]
        m15_assessment = assessments[Timeframe.M15]
        if m15_assessment.regime == MarketRegime.UNTRADEABLE:
            return None, None
        if not m15.available or not m15.bars:
            return None, None

        current_price = m15.bars[-1].close
        context = StrategyContext(
            pair=pair,
            regime=m15_assessment.regime.value,
            bars={tf.value: snapshot.bars for tf, snapshot in snapshots.items()},
            current_price=current_price,
            regimes={tf.value: assessment.regime.value for tf, assessment in assessments.items()},
        )
        selection = self.strategy_selector.evaluate(context)
        candidate = selection.selected
        if candidate is None:
            return None, None

        if 70.0 <= candidate.score < 75.0:
            levels = self._technical_levels(m15, candidate.direction, current_price)
            if levels is None:
                return None, None
            stop_loss, take_profit = levels
            direction = Direction.BUY if candidate.direction == "BUY" else Direction.SELL
            return Signal(
                signal_id=uuid4(),
                pair=pair,
                direction=direction,
                strategy=candidate.strategy,
                market_regime=m15_assessment.regime,
                current_price=current_price,
                entry=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                risk_reward=2.0,
                score=candidate.score,
                confidence=min(100.0, m15_assessment.confidence),
                trigger="score threshold reached",
                invalidation="risk vetting required",
                expiry=now + timedelta(minutes=MIN_EXECUTION_WINDOW_MINUTES),
                timeframes=(Timeframe.M15, Timeframe.H1, Timeframe.H4),
                evidence=tuple(Evidence(e, 1.0, 1.0, "analysis") for e in candidate.evidence),
                timestamp=now,
                status=SignalStatus.RISK_NOT_VETTED,
            ), None

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

        levels = self._technical_levels(m15, setup.direction, current_price)
        if levels is None:
            return None, None
        stop_loss, take_profit = levels
        direction = Direction.BUY if setup.direction == "BUY" else Direction.SELL

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
            market_regime=m15_assessment.regime,
            current_price=current_price,
            entry=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward=2.0,
            score=setup.score,
            confidence=min(100.0, m15_assessment.confidence),
            trigger=setup.trigger,
            invalidation=setup.invalidation,
            expiry=setup.expires_at,
            timeframes=(Timeframe.M15, Timeframe.H1, Timeframe.H4),
            evidence=tuple(Evidence(e, 1.0, 1.0, "analysis") for e in setup.evidence),
            timestamp=now,
            status=SignalStatus.TRIGGERED,
        )
        return signal, position

    def evaluate_and_notify(self, **kwargs: object) -> tuple[Signal | None, PositionSize | None]:
        signal, position = self.evaluate(**kwargs)
        if signal is not None and self.notifier is not None:
            if signal.status is SignalStatus.RISK_NOT_VETTED:
                risk = "NOT VETTED"
            elif position is not None:
                risk = f"0.5% | volume {position.volume:g}"
            else:
                return signal, position
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
                "risk": risk,
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
