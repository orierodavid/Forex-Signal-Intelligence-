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
    """Thin MT5 terminal adapter. It never decides whether an account is safe to trade."""

    def __init__(self, config: MT5Config, mt5_module: Any | None = None) -> None:
        self.config = config
        self.mt5 = mt5_module

    def _module(self) -> Any:
        if self.mt5 is not None:
            return self.mt5
        try:
            import MetaTrader5 as mt5
        except ImportError as exc:  # pragma: no cover - exercised by deployment, not CI
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
        account_type = (
            AccountType.DEMO if trade_mode == demo_value
            else AccountType.LIVE if trade_mode == live_value
            else AccountType.UNKNOWN
        )
        return AccountInfo(
            login=int(getattr(info, "login", 0)),
            server=str(getattr(info, "server", "")),
            account_type=account_type,
            balance=float(getattr(info, "balance", 0.0)),
            equity=float(getattr(info, "equity", 0.0)),
        )

    def symbol_info(self, symbol: str) -> Any:
        mt5 = self._module()
        info = mt5.symbol_info(symbol)
        if info is None:
            raise MT5UnavailableError(f"symbol_info failed for {symbol}: {mt5.last_error()}")
        if not getattr(info, "visible", True):
            if not mt5.symbol_select(symbol, True):
                raise MT5UnavailableError(f"symbol_select failed for {symbol}: {mt5.last_error()}")
        return info

    def tick(self, symbol: str) -> Any:
        mt5 = self._module()
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise MT5UnavailableError(f"symbol_info_tick failed for {symbol}: {mt5.last_error()}")
        return tick

    def submit(self, request: ExecutionRequest) -> ExecutionResult:
        mt5 = self._module()
        self.symbol_info(request.symbol)
        tick = self.tick(request.symbol)
        order_type = mt5.ORDER_TYPE_BUY if request.direction == "BUY" else mt5.ORDER_TYPE_SELL
        price = float(tick.ask if request.direction == "BUY" else tick.bid)
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
        retcode = getattr(result, "retcode", None)
        success = retcode == getattr(mt5, "TRADE_RETCODE_DONE", None)
        if not success:
            return ExecutionResult(False, f"broker rejected order: retcode={retcode}")
        return ExecutionResult(
            accepted=True,
            reason="broker accepted order",
            order_id=getattr(result, "order", None),
            position_id=getattr(result, "position", None),
            fill_price=getattr(result, "price", None),
        )
