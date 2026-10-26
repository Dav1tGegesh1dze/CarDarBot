from __future__ import annotations

import logging

from sqlalchemy import func, select
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from cardarbot.bot.auth import check_rate_limit, require_auth
from cardarbot.bot.callbacks import (
    CB_CANCEL,
    CB_MAIN_MENU,
    CB_MENU_BEST_DEALS,
    CB_MENU_HELP,
    CB_MENU_MARKET_OVERVIEW,
    CB_MENU_MY_SEARCHES,
    CB_MENU_SAVED_CARS,
    CB_MENU_SETTINGS,
    CB_SET_ALERT_LIMIT,
    CB_SET_CITY,
    CB_SET_CURRENCY,
    CB_SET_DAILY_SUMMARY,
    CB_SET_LANGUAGE,
    CB_SET_MAX_PRICE,
    CB_SET_MIN_PROFIT,
    CB_SET_NOTIFICATIONS,
    CB_SET_QUIET_HOURS,
    CB_SET_SCORE,
)
from cardarbot.bot.keyboards import (
    build_back_to_main_keyboard,
    build_main_menu_keyboard,
    build_settings_keyboard,
    build_settings_preset_keyboard,
)
from cardarbot.config import Settings
from cardarbot.database.models import (
    DealEvaluationModel,
    ListingModel,
    ScanJobModel,
    SearchProfileModel,
)
from cardarbot.database.repositories import DealRepository, UserRepository
from cardarbot.database.session import DatabaseManager
from cardarbot.utils.logging import format_tbilisi_time

logger = logging.getLogger("cardarbot.handlers.core")

WELCOME_MESSAGE = (
    "🚗 Welcome to CarDarBot!\n\n"
    "Find undervalued cars in Georgia and discover potential resale opportunities.\n\n"
    "Main menu:"
)

HELP_MESSAGE = (
    "❓ CarDarBot Help & Commands\n\n"
    "Commands:\n"
    "/start — Open the main menu\n"
    "/newsearch — Launch the 17-step Search Creation Wizard\n"
    "/searches — View, run, edit, pause, duplicate, or delete saved searches\n"
    "/deals — Browse evaluated car flip opportunities\n"
    "/saved — View your saved listings\n"
    "/settings — Configure default price, profit, score, notifications, and language\n"
    "/stats — View market overview & database statistics\n"
    "/scan — Run a manual scan across active searches\n"
    "/status — Check bot, scheduler, and MyAuto source health\n"
    "/cancel — Cancel any active wizard or operation\n"
    "/help — Show this guide\n\n"
    "💡 Tip: You can also type natural language queries directly, such as:\n"
    '• "Find Toyota Prius under $4000"\n'
    '• "Electric cars under $5000"\n'
    '• "BMW coupe 2012-2018"\n'
    '• "Find 4x4 under $3000"\n'
    "Or upload a `.json` / `.csv` / `.html` export file to import listings!"
)


def _ensure_user_and_settings(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> tuple[int, int]:
    """Ensure the authorized Telegram user exists in SQLite and return (db_user_id, tg_user_id)."""
    db: DatabaseManager = context.application.bot_data["db"]
    settings: Settings = context.application.bot_data["settings"]
    tg_user = update.effective_user
    assert tg_user is not None
    with db.session() as session:
        repo = UserRepository(session)
        user = repo.get_or_create_user(
            telegram_user_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            default_max_price_usd=settings.default_max_price_usd,
            default_min_profit_usd=settings.default_min_profit_usd,
            default_city=settings.default_city,
            default_min_score=settings.default_min_deal_score,
            max_alerts_per_scan=settings.max_alerts_per_scan,
        )
        return user.id, tg_user.id


@require_auth
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /start and display the exact welcome screen and main menu."""
    _ensure_user_and_settings(update, context)
    if context.user_data is not None:
        context.user_data.clear()

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            WELCOME_MESSAGE,
            reply_markup=build_main_menu_keyboard(),
        )
    elif update.effective_message:
        await update.effective_message.reply_text(
            WELCOME_MESSAGE,
            reply_markup=build_main_menu_keyboard(),
        )
    return ConversationHandler.END


@require_auth
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help and display command reference."""
    _ensure_user_and_settings(update, context)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            HELP_MESSAGE,
            reply_markup=build_back_to_main_keyboard(),
        )
    elif update.effective_message:
        await update.effective_message.reply_text(
            HELP_MESSAGE,
            reply_markup=build_back_to_main_keyboard(),
        )


@require_auth
async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /cancel and return to Main Menu."""
    if context.user_data is not None:
        context.user_data.clear()
    text = "❌ Operation cancelled. Returned to Main Menu."
    if update.callback_query:
        await update.callback_query.answer("Cancelled")
        await update.callback_query.edit_message_text(
            text + "\n\n" + WELCOME_MESSAGE,
            reply_markup=build_main_menu_keyboard(),
        )
    elif update.effective_message:
        await update.effective_message.reply_text(
            text + "\n\n" + WELCOME_MESSAGE,
            reply_markup=build_main_menu_keyboard(),
        )
    return ConversationHandler.END


@require_auth
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /settings and display interactive user settings."""
    user_id, _ = _ensure_user_and_settings(update, context)
    db: DatabaseManager = context.application.bot_data["db"]
    with db.session() as session:
        repo = UserRepository(session)
        tg_id = update.effective_user.id  # type: ignore[union-attr]
        user = repo.get_by_telegram_id(tg_id)
        assert user is not None and user.settings is not None
        s = user.settings
        quiet_str = (
            f"{s.quiet_hours_start:02d}:00–{s.quiet_hours_end:02d}:00"
            if s.quiet_hours_start is not None and s.quiet_hours_end is not None
            else "Disabled"
        )
        text = (
            "⚙️ CarDarBot Settings\n\n"
            f"• Default Maximum Price: ${s.default_max_price_usd:,}\n"
            f"• Default Minimum Profit: ${s.default_min_profit_usd:,}\n"
            f"• Default City: {s.default_city}\n"
            f"• Default Minimum Score: {s.default_min_score}/100\n"
            f"• Preferred Currency: {s.preferred_currency}\n"
            f"• Notifications: {'Enabled' if s.notifications_enabled else 'Paused'}\n"
            f"• Quiet Hours: {quiet_str}\n"
            f"• Daily Summary: {'Enabled' if s.daily_summary_enabled else 'Disabled'}\n"
            f"• Alert Limit: {s.max_alerts_per_scan} per scan\n"
            f"• Preferred Language: {s.preferred_language.upper()}\n\n"
            "Select a setting below to modify:"
        )
        kb = build_settings_keyboard(s)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=kb)
    elif update.effective_message:
        await update.effective_message.reply_text(text, reply_markup=kb)


@require_auth
async def settings_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline button presses for modifying user settings."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    user_id, _ = _ensure_user_and_settings(update, context)
    db: DatabaseManager = context.application.bot_data["db"]
    data = query.data

    # Toggle switches
    if data in {CB_SET_NOTIFICATIONS, CB_SET_DAILY_SUMMARY}:
        with db.session() as session:
            repo = UserRepository(session)
            user = repo.get_by_telegram_id(update.effective_user.id)  # type: ignore[union-attr]
            assert user is not None and user.settings is not None
            if data == CB_SET_NOTIFICATIONS:
                repo.update_settings(
                    user_id, notifications_enabled=not user.settings.notifications_enabled
                )
            else:
                repo.update_settings(
                    user_id, daily_summary_enabled=not user.settings.daily_summary_enabled
                )
        await settings_command(update, context)
        return

    # Preset selection menu
    if data.startswith("set:"):
        await query.answer()
        labels = {
            CB_SET_MAX_PRICE: "Select Default Maximum Purchase Price (USD):",
            CB_SET_MIN_PROFIT: "Select Default Minimum Expected Net Profit (USD):",
            CB_SET_CITY: "Select Default Location (Only Tbilisi is supported initially):",
            CB_SET_SCORE: "Select Default Deal Score Threshold (0–100):",
            CB_SET_CURRENCY: "Select Preferred Display Currency:",
            CB_SET_ALERT_LIMIT: "Select Maximum Alerts Per Scan:",
            CB_SET_QUIET_HOURS: "Select Quiet Hours (Asia/Tbilisi time):",
            CB_SET_LANGUAGE: "Select Preferred Language:",
        }
        prompt_text = labels.get(data, "Select value:")
        await query.edit_message_text(
            prompt_text,
            reply_markup=build_settings_preset_keyboard(data),
        )
        return

    # Apply preset value
    if data.startswith("setval:"):
        _, field_key, raw_val = data.split(":", 2)
        with db.session() as session:
            repo = UserRepository(session)
            if field_key == "max_price":
                repo.update_settings(user_id, default_max_price_usd=int(raw_val))
            elif field_key == "min_profit":
                repo.update_settings(user_id, default_min_profit_usd=int(raw_val))
            elif field_key == "score":
                repo.update_settings(user_id, default_min_score=int(raw_val))
            elif field_key == "currency":
                repo.update_settings(user_id, preferred_currency=raw_val)
            elif field_key == "limit":
                repo.update_settings(user_id, max_alerts_per_scan=int(raw_val))
            elif field_key == "city":
                repo.update_settings(user_id, default_city=raw_val)
            elif field_key == "lang":
                repo.update_settings(user_id, preferred_language=raw_val)
            elif field_key == "quiet":
                if raw_val == "off":
                    repo.update_settings(user_id, quiet_hours_start=None, quiet_hours_end=None)
                else:
                    start_h, end_h = raw_val.split("_")
                    repo.update_settings(
                        user_id, quiet_hours_start=int(start_h), quiet_hours_end=int(end_h)
                    )
        await query.answer("✅ Setting updated!")
        await settings_command(update, context)


@require_auth
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stats and 📊 Market Overview."""
    user_id, _ = _ensure_user_and_settings(update, context)
    db: DatabaseManager = context.application.bot_data["db"]
    with db.session() as session:
        total_listings = session.scalar(select(func.count(ListingModel.id))) or 0
        clean_listings = (
            session.scalar(
                select(func.count(ListingModel.id)).where(
                    ListingModel.is_spam_or_rejected.is_(False)
                )
            )
            or 0
        )
        rejected_listings = total_listings - clean_listings
        avg_price = session.scalar(
            select(func.avg(ListingModel.usd_price)).where(
                ListingModel.is_spam_or_rejected.is_(False),
                ListingModel.usd_price.is_not(None),
            )
        )
        qualifying_deals = (
            session.scalar(
                select(func.count(DealEvaluationModel.id)).where(
                    DealEvaluationModel.score >= 70,
                    DealEvaluationModel.hard_rejected.is_(False),
                )
            )
            or 0
        )
        user_searches = (
            session.scalar(
                select(func.count(SearchProfileModel.id)).where(
                    SearchProfileModel.user_id == user_id
                )
            )
            or 0
        )

    avg_str = f"${avg_price:,.0f}" if avg_price else "N/A"
    text = (
        "📊 Market Overview & Statistics\n\n"
        f"• Your Saved Searches: {user_searches}\n"
        f"• Total Tracked Listings: {total_listings}\n"
        f"• Verified Clean Listings: {clean_listings}\n"
        f"• Filtered Spam / Damaged: {rejected_listings}\n"
        f"• Average Clean Asking Price: {avg_str}\n"
        f"• Strong/Exceptional Deals (≥70): {qualifying_deals}\n"
        "• Primary Market: Tbilisi, Georgia"
    )
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text, reply_markup=build_back_to_main_keyboard()
        )
    elif update.effective_message:
        await update.effective_message.reply_text(text, reply_markup=build_back_to_main_keyboard())


@require_auth
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status and report source health, scheduler, and last scan job."""
    _ensure_user_and_settings(update, context)
    db: DatabaseManager = context.application.bot_data["db"]
    settings: Settings = context.application.bot_data["settings"]

    with db.session() as session:
        deal_repo = DealRepository(session)
        health = deal_repo.get_source_health("myauto")
        last_job = session.execute(
            select(ScanJobModel).order_by(ScanJobModel.started_at.desc()).limit(1)
        ).scalar_one_or_none()

        if health is None:
            mode_str = "import_only (Not yet probed)"
            last_check_str = "Never"
            err_str = "None"
        else:
            mode_str = health.status_mode
            last_check_str = format_tbilisi_time(health.last_check_at)
            err_str = health.last_error or "None"

        if last_job is None:
            job_str = "No scan jobs executed yet."
        else:
            job_str = (
                f"Job #{last_job.id} ({last_job.trigger_type}) — {last_job.status}\n"
                f"  Fetched: {last_job.listings_fetched}, Deals: {last_job.deals_found}, "
                f"Alerts: {last_job.alerts_sent}\n"
                f"  Started: {format_tbilisi_time(last_job.started_at)}"
            )

    text = (
        "🩺 CarDarBot Operational Status\n\n"
        f"• Mode: {'DRY_RUN' if settings.dry_run else 'LIVE'}\n"
        f"• MyAuto Source Mode: `{mode_str}`\n"
        f"• Last Source Check: {last_check_str}\n"
        f"• Source Note: {err_str}\n"
        f"• Default Scan Interval: Every {settings.default_scan_interval_hours}h\n\n"
        f"🕒 Latest Scan Job:\n{job_str}"
    )
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text, reply_markup=build_back_to_main_keyboard()
        )
    elif update.effective_message:
        await update.effective_message.reply_text(text, reply_markup=build_back_to_main_keyboard())


@require_auth
async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /scan with rate-limiting and delegate to search_service if registered."""
    user_id, tg_id = _ensure_user_and_settings(update, context)
    allowed, wait_sec = check_rate_limit(tg_id, cooldown_seconds=10.0)
    if not allowed:
        msg = f"⏳ Please wait {wait_sec}s before running another manual scan."
        if update.callback_query:
            await update.callback_query.answer(msg, show_alert=True)
        elif update.effective_message:
            await update.effective_message.reply_text(msg)
        return

    search_service = context.application.bot_data.get("search_service")
    if search_service is not None:
        result_msg = await search_service.run_manual_scan_for_user(
            user_id=user_id, telegram_user_id=tg_id, bot=context.bot
        )
    else:
        result_msg = (
            "🔄 Scan check completed.\n"
            "Create a search profile with /newsearch to scan specific criteria."
        )

    if update.callback_query:
        await update.callback_query.answer("Scan complete")
        await update.callback_query.edit_message_text(
            result_msg, reply_markup=build_back_to_main_keyboard()
        )
    elif update.effective_message:
        await update.effective_message.reply_text(
            result_msg, reply_markup=build_back_to_main_keyboard()
        )


@require_auth
async def navigation_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route main menu and fallback callback queries."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    data = query.data

    if data in {CB_MAIN_MENU, CB_CANCEL}:
        await start_command(update, context)
        return
    if data == CB_MENU_HELP:
        await help_command(update, context)
        return
    if data == CB_MENU_SETTINGS:
        await settings_command(update, context)
        return
    if data == CB_MENU_MARKET_OVERVIEW:
        await stats_command(update, context)
        return

    # Delegate to registered phase handlers if available
    if data == CB_MENU_MY_SEARCHES:
        searches_handler = context.application.bot_data.get("searches_command_handler")
        if searches_handler:
            await searches_handler(update, context)
            return
    if data == CB_MENU_BEST_DEALS:
        deals_handler = context.application.bot_data.get("deals_command_handler")
        if deals_handler:
            await deals_handler(update, context)
            return
    if data == CB_MENU_SAVED_CARS:
        saved_handler = context.application.bot_data.get("saved_command_handler")
        if saved_handler:
            await saved_handler(update, context)
            return

    await query.answer("⚠️ This menu item or session has expired. Returning to Main Menu.")
    await query.edit_message_text(
        WELCOME_MESSAGE,
        reply_markup=build_main_menu_keyboard(),
    )
