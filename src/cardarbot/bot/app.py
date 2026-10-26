from __future__ import annotations

import logging
from typing import Any

from telegram import BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
)

from cardarbot.bot.handlers.core import (
    cancel_command,
    help_command,
    navigation_callback_handler,
    scan_command,
    settings_callback_handler,
    settings_command,
    start_command,
    stats_command,
    status_command,
)
from cardarbot.config import Settings
from cardarbot.database.session import DatabaseManager

logger = logging.getLogger("cardarbot.bot.app")

BOT_COMMANDS: list[BotCommand] = [
    BotCommand("start", "Open CarDarBot main menu"),
    BotCommand("newsearch", "Create a new car search profile"),
    BotCommand("searches", "Manage your saved car searches"),
    BotCommand("deals", "Browse evaluated car flip opportunities"),
    BotCommand("saved", "View your saved listings"),
    BotCommand("settings", "Configure default budget, profit, score, and alerts"),
    BotCommand("stats", "View market overview and statistics"),
    BotCommand("scan", "Run a manual scan across active searches"),
    BotCommand("status", "Check operational and MyAuto source status"),
    BotCommand("cancel", "Cancel current operation"),
    BotCommand("help", "View help and command guide"),
]


async def post_init_setup(application: Application[Any, Any, Any, Any, Any, Any]) -> None:
    """Register Telegram command descriptions on bot startup."""
    try:
        await application.bot.set_my_commands(BOT_COMMANDS)
        logger.info("Registered %d Telegram bot commands.", len(BOT_COMMANDS))
    except Exception as exc:
        logger.warning("Could not set bot commands on startup: %s", exc)


def create_bot_application(
    settings: Settings,
    db: DatabaseManager,
    token_override: str | None = None,
) -> Application[Any, Any, Any, Any, Any, Any]:
    """Build and configure the python-telegram-bot Application with dependency injection."""
    token = token_override or settings.telegram_bot_token.get_secret_value().strip()
    if not token:
        # Use a syntactic placeholder only when building in dry-run/test mode
        token = "100000000:AAH_placeholder_dry_run_token_000000"

    app = ApplicationBuilder().token(token).post_init(post_init_setup).build()
    app.bot_data["settings"] = settings
    app.bot_data["db"] = db

    # Register feature modules if available (Search Wizard, Deals, Import handler)
    for registrar_name in (
        "register_search_handlers",
        "register_deal_handlers",
    ):
        registrar = app.bot_data.get(registrar_name)
        if callable(registrar):
            registrar(app)

    # Core command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("scan", scan_command))
    app.add_handler(CommandHandler("cancel", cancel_command))

    # Settings inline callbacks
    app.add_handler(CallbackQueryHandler(settings_callback_handler, pattern=r"^set(val)?:"))

    # Navigation and fallback callback handler
    app.add_handler(CallbackQueryHandler(navigation_callback_handler))

    return app
