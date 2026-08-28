from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .execution import AccountInfo, AccountType, ExecutionRequest, ExecutionResult


@dataclass(frozen=True)
class MT5Config:
    login: int
    password: str
    server: str
    path: str | None = None


class MT5UnavailableError(RuntimeError):
    pass


class MT5Adapter:
    """Thin MT5 terminal adapter with a broker-side risk fail-safe."""

    def __init__(self, config: MT5Config, mt5_module: Any | None = None) -> None:
        self.config = config
        self.mt5 = mt5_module

    def _module(self) -> Any:
        if self.mt5 is not None:
            return self.mt5
        try:
            import MetaTrader5 as mt5
        except ImportError as exc:
            raise MT5UnavailableError("MetaTrader5 package is not installed") from exc
        self.mt5 = mt5
        return mt5

    def connect(self) -> bool:
        mt5 = self._module()
        kwargs = {"login": self.config.login, "password": self.config.password, "server": self.config.server}
        if self.config.path:
            return bool(mt5.initialize(self.config.path, **kwargs))
        return bool(mt5.initialize(**kwargs))

    def shutdown(self) -> None:
        if self.mt5 is not None:
            self.mt5.shutdown()

    def account_info(self) -> AccountInfo:
        mt5 = self._module()
        info = mt5.account_info()
        if info is None:
            raise MT5UnavailableError(f"MT5 account_info failed: {mt5.last_error()}")
        trade_mode = getattr(info, "trade_mode", None)
        demo_value = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0)
        live_value = getattr(mt5, "ACCOUNT_TRADE_MODE_REAL", 2)
        account_type = AccountType.DEMO if trade_mode == demo_value else AccountType.LIVE if trade_mode == live_value else AccountType.UNKNOWN
        return AccountInfo(int(getattr(info, "login", 0)), str(getattr(info, "server", "")), account_type,
                           float(getattr(info, "balance", 0.0)), float(getattr(info, "equity", 0.0)))

    def symbol_info(self, symbol: str) -> Any:
        mt5 = self._module()
        info = mt5.symbol_info(symbol)
        if info is None:
            raise MT5UnavailableError(f"symbol_info failed for {symbol}: {mt5.last_error()}")
        if not getattr(info, "visible", True) and not mt5.symbol_select(symbol, True):
            raise MT5UnavailableError(f"symbol_select failed for {symbol}: {mt5.last_error()}")
        return info

    def tick(self, symbol: str) -> Any:
        mt5 = self._module()
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise MT5UnavailableError(f"symbol_info_tick failed for {symbol}: {mt5.last_error()}")
        return tick

    def positions(self, symbol: str | None = None) -> tuple[Any, ...]:
        mt5 = self._module()
        rows = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        if rows is None:
            raise MT5UnavailableError(f"positions_get failed: {mt5.last_error()}")
        return tuple(rows)

    def submit(self, request: ExecutionRequest) -> ExecutionResult:
        mt5 = self._module()
        self.symbol_info(request.symbol)
        tick = self.tick(request.symbol)
        order_type = mt5.ORDER_TYPE_BUY if request.direction == "BUY" else mt5.ORDER_TYPE_SELL
        price = float(tick.ask if request.direction == "BUY" else tick.bid)

        if request.direction == "BUY" and request.stop_loss >= price:
            return ExecutionResult(False, "BUY stop-loss must be below current ask")
        if request.direction == "SELL" and request.stop_loss <= price:
            return ExecutionResult(False, "SELL stop-loss must be above current bid")

        account = mt5.account_info()
        if account is None:
            return ExecutionResult(False, f"account_info failed before risk check: {mt5.last_error()}")
        equity = float(getattr(account, "equity", 0.0))
        if equity <= 0:
            return ExecutionResult(False, "account equity is not positive")

        # Use MT5's own contract economics rather than a hard-coded pip/tick
        # assumption. This catches oversized orders such as 0.21 lots on XAUUSD
        # when the broker-calculated loss at SL exceeds the 0.5% risk budget.
        calc = getattr(mt5, "order_calc_profit", None)
        if not callable(calc):
            return ExecutionResult(False, "broker risk calculation unavailable; order blocked")
        estimated_pnl = calc(order_type, request.symbol, request.volume, price, request.stop_loss)
        if estimated_pnl is None:
            return ExecutionResult(False, f"broker risk calculation failed: {mt5.last_error()}")
        estimated_loss = max(0.0, -float(estimated_pnl))
        max_loss = equity * request.max_risk_fraction
        if estimated_loss > max_loss + 1e-9:
            return ExecutionResult(
                False,
                f"risk cap blocked order: estimated SL loss ${estimated_loss:.2f} > max ${max_loss:.2f}",
            )

        trade_request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": request.symbol,
            "volume": request.volume,
            "type": order_type,
            "price": price,
            "sl": request.stop_loss,
            "tp": request.take_profit,
            "deviation": 20,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
            "comment": f"FSI:{request.signal_id}",
        }
        result = mt5.order_send(trade_request)
        if result is None:
            return ExecutionResult(False, f"order_send returned no result: {mt5.last_error()}")
        if getattr(result, "retcode", None) != getattr(mt5, "TRADE_RETCODE_DONE", None):
            return ExecutionResult(False, f"broker rejected order: retcode={getattr(result, 'retcode', None)}")
        return ExecutionResult(True, "broker accepted order", getattr(result, "order", None),
                               getattr(result, "position", None), getattr(result, "price", None))
