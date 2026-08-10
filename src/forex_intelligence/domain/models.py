from datetime import datetime
from enum import Enum
from typing import Mapping
from uuid import UUID


class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    NO_TRADE = "NO_TRADE"


class MarketRegime(str, Enum):
    STRONG_TREND_UP = "STRONG_TREND_UP"
    TREND_UP = "TREND_UP"
    RANGE = "RANGE"
    TRANSITION = "TRANSITION"
    TREND_DOWN = "TREND_DOWN"
    STRONG_TREND_DOWN = "STRONG_TREND_DOWN"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    UNTRADEABLE = "UNTRADEABLE"


class SignalStatus(str, Enum):
    WATCHING = "WATCHING"
    READY = "READY"
    TRIGGERED = "TRIGGERED"
    RISK_NOT_VETTED = "RISK_NOT_VETTED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"


class Timeframe(str, Enum):
    H4 = "H4"
    H1 = "H1"
    M15 = "M15"
    M5 = "M5"


class Evidence:
    """Immutable-style evidence record used to make decisions auditable."""

    __slots__ = ("name", "value", "weight", "source")

    def __init__(self, name: str, value: float, weight: float, source: str) -> None:
        if not name or not source:
            raise ValueError("Evidence name and source are required")
        if not 0 <= value <= 1:
            raise ValueError("Evidence value must be between 0 and 1")
        if weight < 0:
            raise ValueError("Evidence weight cannot be negative")
        self.name = name
        self.value = value
        self.weight = weight
        self.source = source

    def as_dict(self) -> dict[str, object]:
        return {"name": self.name, "value": self.value, "weight": self.weight, "source": self.source}


class Signal:
    """Canonical signal contract shared by analysis, persistence, Telegram and execution."""

    def __init__(
        self,
        signal_id: UUID,
        pair: str,
        direction: Direction,
        strategy: str,
        market_regime: MarketRegime,
        current_price: float,
        entry: float,
        stop_loss: float,
        take_profit: float,
        risk_reward: float,
        score: float,
        confidence: float,
        trigger: str,
        invalidation: str,
        expiry: datetime,
        timeframes: tuple[Timeframe, ...],
        evidence: tuple[Evidence, ...],
        timestamp: datetime,
        status: SignalStatus = SignalStatus.WATCHING,
    ) -> None:
        if not pair or not strategy:
            raise ValueError("pair and strategy are required")
        if not 0 <= score <= 100 or not 0 <= confidence <= 100:
            raise ValueError("score and confidence must be between 0 and 100")
        if risk_reward < 0:
            raise ValueError("risk_reward cannot be negative")
        if expiry <= timestamp:
            raise ValueError("expiry must be later than timestamp")
        self.signal_id = signal_id
        self.pair = pair.upper()
        self.direction = direction
        self.strategy = strategy
        self.market_regime = market_regime
        self.current_price = current_price
        self.entry = entry
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.risk_reward = risk_reward
        self.score = score
        self.confidence = confidence
        self.trigger = trigger
        self.invalidation = invalidation
        self.expiry = expiry
        self.timeframes = timeframes
        self.evidence = evidence
        self.timestamp = timestamp
        self.status = status

    def as_dict(self) -> Mapping[str, object]:
        return {
            "signal_id": str(self.signal_id), "pair": self.pair, "direction": self.direction.value,
            "strategy": self.strategy, "market_regime": self.market_regime.value,
            "current_price": self.current_price, "entry": self.entry, "stop_loss": self.stop_loss,
            "take_profit": self.take_profit, "risk_reward": self.risk_reward, "score": self.score,
            "confidence": self.confidence, "trigger": self.trigger, "invalidation": self.invalidation,
            "expiry": self.expiry.isoformat(), "timeframes": [t.value for t in self.timeframes],
            "evidence": [e.as_dict() for e in self.evidence], "timestamp": self.timestamp.isoformat(),
            "status": self.status.value,
        }
