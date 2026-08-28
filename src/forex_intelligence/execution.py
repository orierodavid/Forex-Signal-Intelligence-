from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class ExecutionMode(str, Enum):
    ANALYSIS_ONLY = "ANALYSIS_ONLY"
    DEMO_EXECUTION = "DEMO_EXECUTION"
    LIVE_DISABLED = "LIVE_DISABLED"


class AccountType(str, Enum):
    DEMO = "DEMO"
    LIVE = "LIVE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class AccountInfo:
    login: int
    server: str
    account_type: AccountType
    balance: float
    equity: float


@dataclass(frozen=True)
class ExecutionRequest:
    signal_id: str
    symbol: str
    direction: str
    volume: float
    entry: float
    stop_loss: float
    take_profit: float
    max_risk_fraction: float = 0.005


@dataclass(frozen=True)
class ExecutionResult:
    accepted: bool
    reason: str
    order_id: int | None = None
    position_id: int | None = None
    fill_price: float | None = None


class TradingAdapter(Protocol):
    def account_info(self) -> AccountInfo: ...

    def submit(self, request: ExecutionRequest) -> ExecutionResult: ...


class ExecutionGate:
    """Hard safety boundary between validated signals and broker execution."""

    def __init__(self, *, mode: ExecutionMode, allowed_demo_login: int | None = None,
                 allowed_demo_server: str | None = None) -> None:
        self.mode = mode
        self.allowed_demo_login = allowed_demo_login
        self.allowed_demo_server = allowed_demo_server

    def validate_account(self, account: AccountInfo) -> tuple[bool, str]:
        if self.mode != ExecutionMode.DEMO_EXECUTION:
            return False, f"execution mode {self.mode.value} does not permit orders"
        if account.account_type is not AccountType.DEMO:
            return False, "live or unknown account detected; demo execution blocked"
        if self.allowed_demo_login is not None and account.login != self.allowed_demo_login:
            return False, "connected demo login is not authorized"
        if self.allowed_demo_server is not None and account.server != self.allowed_demo_server:
            return False, "connected demo server is not authorized"
        if account.balance <= 0 or account.equity <= 0:
            return False, "demo account has no positive balance/equity"
        return True, "demo account verified"

    def submit(self, adapter: TradingAdapter, request: ExecutionRequest) -> ExecutionResult:
        if request.direction not in {"BUY", "SELL"}:
            return ExecutionResult(False, "invalid execution direction")
        if request.volume <= 0:
            return ExecutionResult(False, "execution volume must be positive")
        if not 0 < request.max_risk_fraction <= 0.005:
            return ExecutionResult(False, "requested risk fraction exceeds 0.5% hard cap")
        if request.stop_loss <= 0 or request.take_profit <= 0 or request.entry <= 0:
            return ExecutionResult(False, "invalid entry/stop/target")

        account = adapter.account_info()
        allowed, reason = self.validate_account(account)
        if not allowed:
            return ExecutionResult(accepted=False, reason=reason)

        return adapter.submit(request)
