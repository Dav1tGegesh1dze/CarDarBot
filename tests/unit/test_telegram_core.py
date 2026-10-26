from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from cardarbot.bot.app import BOT_COMMANDS, create_bot_application
from cardarbot.bot.auth import is_user_authorized, reset_rate_limits
from cardarbot.bot.callbacks import (
    CB_MAIN_MENU,
    CB_MENU_HELP,
    CB_MENU_MARKET_OVERVIEW,
    CB_MENU_SETTINGS,
    CB_SET_MAX_PRICE,
    CB_SET_NOTIFICATIONS,
)
from cardarbot.bot.handlers.core import (
    WELCOME_MESSAGE,
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


def _make_mock_update_and_context(
    user_id: int = 777001,
    allowed_ids: list[int] | None = None,
    callback_data: str | None = None,
) -> tuple[MagicMock, MagicMock, DatabaseManager]:
    db = DatabaseManager("sqlite:///:memory:")
    db.init_db()
    settings = Settings(
        TELEGRAM_BOT_TOKEN="123456789:ABCDEF1234567890abcdef1234567890",
        TELEGRAM_ALLOWED_USER_IDS=allowed_ids if allowed_ids is not None else [777001],
    )

    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.username = "tester"
    update.effective_user.first_name = "TestUser"

    if callback_data is not None:
        update.callback_query = MagicMock()
        update.callback_query.data = callback_data
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        update.effective_message = None
    else:
        update.callback_query = None
        update.effective_message = MagicMock()
        update.effective_message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {}
    context.application.bot_data = {"settings": settings, "db": db}
    context.bot = AsyncMock()

    return update, context, db


def test_bot_application_builder_and_commands() -> None:
    db = DatabaseManager("sqlite:///:memory:")
    db.init_db()
    settings = Settings(TELEGRAM_ALLOWED_USER_IDS=[777001])
    app = create_bot_application(settings=settings, db=db)
    assert app.bot_data["settings"] == settings
    assert app.bot_data["db"] == db
    cmd_names = {c.command for c in BOT_COMMANDS}
    expected = {
        "start",
        "help",
        "newsearch",
        "searches",
        "deals",
        "saved",
        "settings",
        "stats",
        "scan",
        "status",
        "cancel",
    }
    assert expected == cmd_names


@pytest.mark.asyncio
async def test_authorization_rejection_and_acceptance() -> None:
    s_empty = Settings(TELEGRAM_ALLOWED_USER_IDS=[])
    assert is_user_authorized(777001, s_empty) is False

    # Unauthorized user trying /start
    update_unauth, ctx_unauth, _ = _make_mock_update_and_context(
        user_id=999999, allowed_ids=[777001]
    )
    await start_command(update_unauth, ctx_unauth)
    update_unauth.effective_message.reply_text.assert_awaited_once()
    args, _ = update_unauth.effective_message.reply_text.call_args
    assert "Access Denied" in args[0]

    # Authorized user running /start
    update_auth, ctx_auth, _ = _make_mock_update_and_context(user_id=777001, allowed_ids=[777001])
    await start_command(update_auth, ctx_auth)
    update_auth.effective_message.reply_text.assert_awaited_once()
    args_ok, kwargs_ok = update_auth.effective_message.reply_text.call_args
    assert args_ok[0] == WELCOME_MESSAGE
    assert kwargs_ok["reply_markup"] is not None


@pytest.mark.asyncio
async def test_settings_flow_and_persistence() -> None:
    update, ctx, _ = _make_mock_update_and_context(user_id=777001)
    await settings_command(update, ctx)
    update.effective_message.reply_text.assert_awaited_once()
    msg_text = update.effective_message.reply_text.call_args[0][0]
    assert "Default Maximum Price: $5,000" in msg_text

    # Toggle notifications via callback
    update.callback_query = MagicMock()
    update.callback_query.data = CB_SET_NOTIFICATIONS
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    await settings_callback_handler(update, ctx)
    edited_text = update.callback_query.edit_message_text.call_args[0][0]
    assert "Notifications: Paused" in edited_text

    # Open preset for max price
    update.callback_query.data = CB_SET_MAX_PRICE
    await settings_callback_handler(update, ctx)
    assert (
        "Select Default Maximum Purchase Price"
        in (update.callback_query.edit_message_text.call_args[0][0])
    )

    # Apply preset value $7,500
    update.callback_query.data = "setval:max_price:7500"
    await settings_callback_handler(update, ctx)
    edited_after = update.callback_query.edit_message_text.call_args[0][0]
    assert "Default Maximum Price: $7,500" in edited_after


@pytest.mark.asyncio
async def test_help_stats_status_cancel_and_rate_limit() -> None:
    reset_rate_limits()
    update, ctx, _ = _make_mock_update_and_context(user_id=777001)

    await help_command(update, ctx)
    assert "/newsearch" in update.effective_message.reply_text.call_args[0][0]

    await stats_command(update, ctx)
    assert "Market Overview" in update.effective_message.reply_text.call_args[0][0]

    await status_command(update, ctx)
    assert "Operational Status" in update.effective_message.reply_text.call_args[0][0]

    await cancel_command(update, ctx)
    assert "Operation cancelled" in update.effective_message.reply_text.call_args[0][0]

    # Rate limit on /scan
    await scan_command(update, ctx)
    assert "Scan check completed" in update.effective_message.reply_text.call_args[0][0]

    await scan_command(update, ctx)
    assert "Please wait" in update.effective_message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_navigation_callbacks() -> None:
    for cb in (CB_MAIN_MENU, CB_MENU_HELP, CB_MENU_SETTINGS, CB_MENU_MARKET_OVERVIEW, "unknown:cb"):
        update, ctx, _ = _make_mock_update_and_context(user_id=777001, callback_data=cb)
        await navigation_callback_handler(update, ctx)
        update.callback_query.edit_message_text.assert_awaited()
