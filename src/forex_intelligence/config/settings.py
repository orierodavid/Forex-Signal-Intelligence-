from enum import Enum
from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ExecutionMode(str, Enum):
    ANALYSIS_ONLY = "ANALYSIS_ONLY"
    DEMO_PAPER = "DEMO_PAPER"
    DEMO_EXECUTION = "DEMO_EXECUTION"
    LIVE_DISABLED = "LIVE_DISABLED"


DEFAULT_PAIRS = (
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD",
    "AUDUSD", "NZDUSD", "EURJPY", "GBPJPY",
)
DEFAULT_SESSIONS = ("ASIA", "LONDON", "NEW_YORK", "OVERLAP")


class Settings(BaseSettings):
    """Runtime configuration with safe, non-trading defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    execution_mode: ExecutionMode = ExecutionMode.ANALYSIS_ONLY
    execution_enabled: bool = False
    emergency_stop: bool = False

    mt5_login: int | None = None
    mt5_password: str | None = Field(default=None, repr=False)
    mt5_server: str | None = None
    mt5_terminal_path: str | None = None

    market_data_provider: str = "mt5"
    market_data_api_key: str | None = Field(default=None, repr=False)

    max_risk_per_trade: Annotated[float, Field(gt=0, le=0.05)] = 0.005
    max_daily_loss: Annotated[float, Field(gt=0, le=1)] = 0.02
    max_open_positions: Annotated[int, Field(ge=1, le=100)] = 3
    max_trades_per_day: Annotated[int, Field(ge=1, le=1000)] = 5
    max_lot_size: Annotated[float, Field(gt=0)] = 1.0
    max_spread_points: Annotated[int, Field(ge=0)] = 30
    max_sl_distance_points: Annotated[int, Field(gt=0)] = 5000

    allowed_pairs: tuple[str, ...] = DEFAULT_PAIRS
    allowed_sessions: tuple[str, ...] = DEFAULT_SESSIONS

    @field_validator("allowed_pairs", "allowed_sessions", mode="before")
    @classmethod
    def parse_csv(cls, value: object) -> tuple[str, ...]:
        if isinstance(value, str):
            return tuple(item.strip().upper() for item in value.split(",") if item.strip())
        if isinstance(value, (list, tuple, set)):
            return tuple(str(item).strip().upper() for item in value if str(item).strip())
        raise TypeError("Expected a comma-separated string or sequence")

    def validate_execution_safety(self) -> None:
        """Reject unsafe execution configuration before any broker adapter is used."""
        if self.execution_mode == ExecutionMode.DEMO_EXECUTION and not self.execution_enabled:
            raise ValueError("DEMO_EXECUTION requires EXECUTION_ENABLED=true")
        if self.execution_mode == ExecutionMode.LIVE_DISABLED and self.execution_enabled:
            raise ValueError("LIVE_DISABLED cannot be execution-enabled")
        if self.execution_mode in {ExecutionMode.ANALYSIS_ONLY, ExecutionMode.DEMO_PAPER} and self.execution_enabled:
            raise ValueError(f"{self.execution_mode.value} must not enable broker execution")

    @property
    def startup_banner(self) -> str:
        return f"EXECUTION MODE: {self.execution_mode.value}"


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    settings = Settings()
    settings.validate_execution_safety()
    return settings
