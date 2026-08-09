import logging
from typing import Mapping

SENSITIVE_KEYS = frozenset({"password", "mt5_password", "api_key", "market_data_api_key", "token", "secret"})


def sanitize_log_fields(fields: Mapping[str, object]) -> dict[str, object]:
    """Redact credentials before structured fields reach logs/telemetry."""
    return {key: "[REDACTED]" if key.lower() in SENSITIVE_KEYS else value for key, value in fields.items()}


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    return logging.getLogger("forex_intelligence")
