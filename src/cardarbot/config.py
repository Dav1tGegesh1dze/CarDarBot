from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    telegram_bot_token: SecretStr = Field(default=SecretStr(""), alias="TELEGRAM_BOT_TOKEN")
    telegram_allowed_user_ids: Annotated[list[int], NoDecode] = Field(
        default_factory=list, alias="TELEGRAM_ALLOWED_USER_IDS"
    )

    database_url: str = Field(default="sqlite:///data/cardarbot.db", alias="DATABASE_URL")

    default_city: str = Field(default="Tbilisi", alias="DEFAULT_CITY")
    default_max_price_usd: int = Field(
        default=5000, ge=100, le=500000, alias="DEFAULT_MAX_PRICE_USD"
    )
    default_min_profit_usd: int = Field(
        default=500, ge=0, le=100000, alias="DEFAULT_MIN_PROFIT_USD"
    )
    default_min_deal_score: int = Field(default=70, ge=0, le=100, alias="DEFAULT_MIN_DEAL_SCORE")

    min_comparables: int = Field(default=5, ge=1, le=100, alias="MIN_COMPARABLES")
    resale_discount_percent: float = Field(
        default=10.0, ge=0.0, le=50.0, alias="RESALE_DISCOUNT_PERCENT"
    )
    default_expense_buffer_usd: int = Field(
        default=400, ge=0, le=50000, alias="DEFAULT_EXPENSE_BUFFER_USD"
    )

    default_scan_interval_hours: int = Field(
        default=24, ge=1, le=168, alias="DEFAULT_SCAN_INTERVAL_HOURS"
    )
    max_alerts_per_scan: int = Field(default=10, ge=1, le=100, alias="MAX_ALERTS_PER_SCAN")

    dry_run: bool = Field(default=True, alias="DRY_RUN")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Documented exchange rate defaults (GEL & EUR to USD)
    gel_to_usd_rate: float = Field(default=0.3676, gt=0.0, alias="GEL_TO_USD_RATE")
    eur_to_usd_rate: float = Field(default=1.08, gt=0.0, alias="EUR_TO_USD_RATE")

    @field_validator("telegram_allowed_user_ids", mode="before")
    @classmethod
    def parse_allowed_user_ids(cls, value: object) -> list[int]:
        if value is None or value == "":
            return []
        if isinstance(value, int):
            return [value]
        if isinstance(value, list):
            return [int(item) for item in value if str(item).strip()]
        if isinstance(value, str):
            cleaned = value.strip().strip("[]")
            if not cleaned:
                return []
            parts = [part.strip() for part in cleaned.split(",") if part.strip()]
            result: list[int] = []
            for part in parts:
                try:
                    result.append(int(part))
                except ValueError as exc:
                    raise ValueError(f"Invalid Telegram user ID '{part}'") from exc
            return result
        raise ValueError("Invalid format for TELEGRAM_ALLOWED_USER_IDS")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        upper = value.upper().strip()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if upper not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}")
        return upper

    def ensure_directories(self) -> None:
        """Ensure required local directories exist for SQLite and logs."""
        if self.database_url.startswith("sqlite:///") and ":memory:" not in self.database_url:
            db_path_str = self.database_url.replace("sqlite:///", "", 1)
            db_path = Path(db_path_str)
            if db_path.parent:
                db_path.parent.mkdir(parents=True, exist_ok=True)
        Path("logs").mkdir(parents=True, exist_ok=True)

    def has_valid_bot_token(self) -> bool:
        token = self.telegram_bot_token.get_secret_value().strip()
        return bool(token and ":" in token and len(token) >= 20)


def get_settings() -> Settings:
    return Settings()
