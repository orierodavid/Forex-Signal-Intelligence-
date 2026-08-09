from forex_intelligence.observability.logging import sanitize_log_fields


def test_sensitive_fields_are_redacted() -> None:
    result = sanitize_log_fields({"mt5_password": "secret", "pair": "EURUSD", "score": 91})
    assert result["mt5_password"] == "[REDACTED]"
    assert result["pair"] == "EURUSD"
