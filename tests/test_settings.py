import pytest

from forex_intelligence.config.settings import ExecutionMode, Settings


def test_safe_default_is_analysis_only() -> None:
    settings = Settings()
    settings.validate_execution_safety()
    assert settings.execution_mode is ExecutionMode.ANALYSIS_ONLY
    assert settings.execution_enabled is False


def test_demo_execution_requires_explicit_enable() -> None:
    with pytest.raises(ValueError, match="EXECUTION_ENABLED"):
        Settings(execution_mode=ExecutionMode.DEMO_EXECUTION, execution_enabled=False).validate_execution_safety()


def test_csv_pair_configuration_is_normalized() -> None:
    settings = Settings(allowed_pairs="eurusd, GBPUSD")
    assert settings.allowed_pairs == ("EURUSD", "GBPUSD")


def test_credentials_are_not_represented() -> None:
    settings = Settings(mt5_password="super-secret")
    assert "super-secret" not in repr(settings)
