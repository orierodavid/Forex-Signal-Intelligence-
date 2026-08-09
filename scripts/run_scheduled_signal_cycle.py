"""Run one scheduled signal cycle and deliver qualified signals to Telegram."""
from __future__ import annotations

import os
import sys


def main() -> int:
    # Scheduling is supplied by the hosting platform. The actual signal producer
    # will call forex_intelligence.scheduled.deliver_qualified_signal. This entry
    # point intentionally has no broker/MT5 execution capability.
    if os.getenv("SIGNAL_CYCLE_ENABLED", "false").lower() != "true":
        print("Signal cycle disabled; no trade signal delivered.")
        return 0

    print("Signal cycle enabled; awaiting the configured signal producer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
