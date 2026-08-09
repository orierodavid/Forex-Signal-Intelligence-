from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Mapping

from forex_intelligence.domain.models import Timeframe


class MarketDataProvider(ABC):
    """Broker-independent market-data contract."""

    @abstractmethod
    def health(self) -> Mapping[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_bars(self, pair: str, timeframe: Timeframe, limit: int) -> list[Mapping[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_quote(self, pair: str) -> Mapping[str, Any]:
        raise NotImplementedError


class ExecutionBroker(ABC):
    """Execution contract; concrete MT5/Exness adapters live outside the analysis engine."""

    @abstractmethod
    def connect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def health(self) -> Mapping[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def symbol_spec(self, pair: str) -> Mapping[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def positions(self, pair: str | None = None) -> list[Mapping[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def submit_order(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def deals(self, start: datetime, end: datetime, pair: str | None = None) -> list[Mapping[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def disconnect(self) -> None:
        raise NotImplementedError


class NewsProvider(ABC):
    """News abstraction. Unavailable must be explicit rather than inferred as NEWS_CLEAR."""

    @abstractmethod
    def health(self) -> Mapping[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_events(self, start: datetime, end: datetime, currencies: list[str]) -> list[Mapping[str, Any]]:
        raise NotImplementedError
