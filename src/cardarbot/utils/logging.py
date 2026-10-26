from __future__ import annotations

import logging
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TBILISI_TZ = ZoneInfo("Asia/Tbilisi")
_TOKEN_PATTERN = re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{30,50}\b")


class SecretRedactingFilter(logging.Filter):
    """Filter that redacts any Telegram Bot Token or secret values from log records."""

    def __init__(self, explicit_secrets: list[str] | None = None) -> None:
        super().__init__()
        self._secrets = [s for s in (explicit_secrets or []) if s and len(s) >= 8]

    def _redact(self, text: str) -> str:
        redacted = _TOKEN_PATTERN.sub("[REDACTED_TELEGRAM_TOKEN]", text)
        for secret in self._secrets:
            if secret in redacted:
                redacted = redacted.replace(secret, "[REDACTED_SECRET]")
        return redacted

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: self._redact(v) if isinstance(v, str) else v for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    self._redact(arg) if isinstance(arg, str) else arg for arg in record.args
                )
        return True


def setup_logging(
    level: str = "INFO",
    log_file: Path | None = None,
    secrets_to_redact: list[str] | None = None,
) -> logging.Logger:
    """Configure application-wide logging with secret redaction."""
    root_logger = logging.getLogger("cardarbot")
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    root_logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    redactor = SecretRedactingFilter(secrets_to_redact)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(redactor)
    root_logger.addHandler(console_handler)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.addFilter(redactor)
        root_logger.addHandler(file_handler)

    # Silence noisy third-party loggers that might log URLs with tokens
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.INFO)

    return root_logger


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(UTC)


def format_tbilisi_time(dt: datetime | None) -> str:
    """Format a UTC or naive datetime into Asia/Tbilisi display string."""
    if dt is None:
        return "Unknown"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    local_dt = dt.astimezone(TBILISI_TZ)
    return local_dt.strftime("%Y-%m-%d %H:%M GET")
