from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

from cardarbot.config import Settings

logger = logging.getLogger("cardarbot.auth")

# Simple in-memory rate limiter for expensive operations (e.g., manual /scan)
_LAST_EXPENSIVE_OP_TS: dict[int, float] = {}


def is_user_authorized(telegram_user_id: int | None, settings: Settings) -> bool:
    """Check if the Telegram user ID is explicitly listed in TELEGRAM_ALLOWED_USER_IDS.

    Security invariant: Private access by default. If TELEGRAM_ALLOWED_USER_IDS is empty,
    nobody is authorized until configured.
    """
    if telegram_user_id is None:
        return False
    if not settings.telegram_allowed_user_ids:
        return False
    return telegram_user_id in settings.telegram_allowed_user_ids


def check_rate_limit(telegram_user_id: int, cooldown_seconds: float = 10.0) -> tuple[bool, int]:
    """Check if a user is within cooldown for an expensive operation.

    Returns:
        (allowed, remaining_seconds)
    """
    now = time.monotonic()
    last = _LAST_EXPENSIVE_OP_TS.get(telegram_user_id)
    if last is not None and (now - last) < cooldown_seconds:
        remaining = int(cooldown_seconds - (now - last)) + 1
        return False, remaining
    _LAST_EXPENSIVE_OP_TS[telegram_user_id] = now
    return True, 0


def reset_rate_limits() -> None:
    """Clear in-memory rate limits (used in tests)."""
    _LAST_EXPENSIVE_OP_TS.clear()


def require_auth(
    func: Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[Any]],
) -> Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[Any]]:
    """Decorator enforcing private access authorization on Telegram handlers."""

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
        settings: Settings = context.application.bot_data["settings"]
        user = update.effective_user
        user_id = user.id if user else None

        if not is_user_authorized(user_id, settings):
            logger.warning("Unauthorized access attempt from Telegram user_id=%s", user_id)
            msg = (
                "🔒 Access Denied.\n\n"
                "CarDarBot is private by default. To authorize your account, add your "
                f"Telegram User ID ({user_id}) to TELEGRAM_ALLOWED_USER_IDS in your local `.env` file."
            )
            if update.callback_query:
                await update.callback_query.answer("🔒 Unauthorized user.", show_alert=True)
            elif update.effective_message:
                await update.effective_message.reply_text(msg)
            return None

        return await func(update, context)

    return wrapper
