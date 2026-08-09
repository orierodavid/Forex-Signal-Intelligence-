from __future__ import annotations

import os
import sys

from forex_intelligence.execution import ExecutionGate, ExecutionMode, ExecutionRequest
from forex_intelligence.mt5_adapter import MT5Adapter, MT5Config, MT5UnavailableError


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"missing required environment variable: {name}")
    return value


def main() -> int:
    if os.getenv("EXECUTION_MODE") != ExecutionMode.DEMO_EXECUTION.value:
        print("DEMO ORDER SMOKE BLOCKED: EXECUTION_MODE must be DEMO_EXECUTION")
        return 2
    if os.getenv("DEMO_ORDER_SMOKE_CONFIRM") != "I_UNDERSTAND_DEMO_ORDER":
        print("DEMO ORDER SMOKE BLOCKED: explicit confirmation is required")
        return 2

    login = int(required("MT5_LOGIN"))
    password = required("MT5_PASSWORD")
    server = required("MT5_SERVER")
    symbol = os.getenv("DEMO_SMOKE_SYMBOL", "EURUSD")
    direction = os.getenv("DEMO_SMOKE_DIRECTION", "BUY")
    volume = float(os.getenv("DEMO_SMOKE_VOLUME", "0.01"))
    entry = float(os.getenv("DEMO_SMOKE_ENTRY", "0"))
    stop_loss = float(required("DEMO_SMOKE_SL"))
    take_profit = float(required("DEMO_SMOKE_TP"))

    adapter = MT5Adapter(MT5Config(login, password, server, os.getenv("MT5_PATH")))
    gate = ExecutionGate(
        mode=ExecutionMode.DEMO_EXECUTION,
        allowed_demo_login=int(os.getenv("MT5_DEMO_LOGIN", str(login))),
        allowed_demo_server=os.getenv("MT5_DEMO_SERVER", server),
    )
    try:
        if not adapter.connect():
            print("MT5 connection failed")
            return 3
        account = adapter.account_info()
        allowed, reason = gate.validate_account(account)
        print(f"ACCOUNT TYPE: {account.account_type.value}")
        print(f"ACCOUNT LOGIN: {account.login}")
        print(f"ACCOUNT SERVER: {account.server}")
        print(f"DEMO GATE: {reason}")
        if not allowed:
            return 4

        tick = adapter.tick(symbol)
        current_entry = float(tick.ask if direction == "BUY" else tick.bid)
        request = ExecutionRequest(
            signal_id="DEMO-SMOKE",
            symbol=symbol,
            direction=direction,
            volume=volume,
            entry=entry or current_entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        result = gate.submit(adapter, request)
        print(f"ORDER ACCEPTED: {result.accepted}")
        print(f"ORDER REASON: {result.reason}")
        print(f"ORDER ID: {result.order_id}")
        print(f"POSITION ID: {result.position_id}")
        print(f"FILL PRICE: {result.fill_price}")
        return 0 if result.accepted else 5
    except MT5UnavailableError as exc:
        print(f"MT5 ERROR: {exc}")
        return 6
    finally:
        adapter.shutdown()


if __name__ == "__main__":
    sys.exit(main())
