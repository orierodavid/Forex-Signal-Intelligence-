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
    mode = os.getenv("EXECUTION_MODE", "ANALYSIS_ONLY")
    if mode != ExecutionMode.DEMO_EXECUTION.value:
        print(f"EXECUTION MODE: {mode}")
        print("Demo execution smoke requires EXECUTION_MODE=DEMO_EXECUTION")
        return 2

    login = int(required("MT5_LOGIN"))
    password = required("MT5_PASSWORD")
    server = required("MT5_SERVER")
    allowed_login = int(os.getenv("MT5_DEMO_LOGIN", str(login)))
    allowed_server = os.getenv("MT5_DEMO_SERVER", server)

    adapter = MT5Adapter(MT5Config(login=login, password=password, server=server, path=os.getenv("MT5_PATH")))
    gate = ExecutionGate(
        mode=ExecutionMode.DEMO_EXECUTION,
        allowed_demo_login=allowed_login,
        allowed_demo_server=allowed_server,
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

        # Deliberately no order is submitted by this smoke script.
        # Order submission belongs to the separately authorized execution path.
        print("DEMO EXECUTION SMOKE: account verification passed; no order submitted")
        return 0
    except MT5UnavailableError as exc:
        print(f"MT5 ERROR: {exc}")
        return 5
    finally:
        adapter.shutdown()


if __name__ == "__main__":
    sys.exit(main())
