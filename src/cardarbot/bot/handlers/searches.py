from __future__ import annotations

import logging
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from cardarbot.bot.auth import check_rate_limit, require_auth
from cardarbot.bot.callbacks import CB_CANCEL, CB_MAIN_MENU, CB_MENU_CREATE_SEARCH
from cardarbot.bot.handlers.core import _ensure_user_and_settings
from cardarbot.bot.handlers.search_wizard import build_search_wizard_conversation_handler
from cardarbot.bot.keyboards import build_main_menu_keyboard
from cardarbot.bot.natural_language import parse_natural_language_search
from cardarbot.database.repositories import SearchProfileRepository, UserRepository
from cardarbot.database.session import DatabaseManager
from cardarbot.domain.search_profiles import SearchFilterConfig, SearchProfileDomain

logger = logging.getLogger("cardarbot.handlers.searches")


def _build_profiles_list_keyboard(profiles: list[SearchProfileDomain]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for p in profiles:
        status_icon = "🟢" if p.is_active else "⏸️"
        rows.append(
            [
                InlineKeyboardButton(
                    f"{status_icon} {p.name} (${p.filters.max_price_usd:,})",
                    callback_data=f"srch:view:{p.id}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton("➕ Create New Search", callback_data=CB_MENU_CREATE_SEARCH),
            InlineKeyboardButton("🏠 Main Menu", callback_data=CB_MAIN_MENU),
        ]
    )
    return InlineKeyboardMarkup(rows)


def _build_profile_detail_keyboard(profile: SearchProfileDomain) -> InlineKeyboardMarkup:
    pid = profile.id
    pause_resume_btn = (
        InlineKeyboardButton("⏸️ Pause", callback_data=f"srch:pause:{pid}")
        if profile.is_active
        else InlineKeyboardButton("▶️ Resume", callback_data=f"srch:resume:{pid}")
    )
    rows = [
        [
            InlineKeyboardButton("🚀 Run Now", callback_data=f"srch:run:{pid}"),
            InlineKeyboardButton("💎 View Results", callback_data=f"deal:profile:{pid}:0"),
        ],
        [
            InlineKeyboardButton("✏️ Edit", callback_data=f"srch:edit:{pid}"),
            pause_resume_btn,
        ],
        [
            InlineKeyboardButton("📋 Duplicate", callback_data=f"srch:dup:{pid}"),
            InlineKeyboardButton("🗑️ Delete", callback_data=f"srch:delask:{pid}"),
        ],
        [
            InlineKeyboardButton("⬅️ Back to My Searches", callback_data="srch:list"),
            InlineKeyboardButton("🏠 Main Menu", callback_data=CB_MAIN_MENU),
        ],
    ]
    return InlineKeyboardMarkup(rows)


@require_auth
async def searches_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /searches and 🚘 My Searches menu button."""
    user_id, _ = _ensure_user_and_settings(update, context)
    db: DatabaseManager = context.application.bot_data["db"]
    with db.session() as session:
        repo = SearchProfileRepository(session)
        profiles = repo.list_user_profiles(user_id)

    if not profiles:
        text = (
            "🚘 **My Searches**\n\n"
            "You do not have any saved search profiles yet.\n"
            "Tap **Create New Search** below or type a query like:\n"
            "`Find Toyota Prius under $4000`"
        )
    else:
        text = (
            f"🚘 **My Searches** ({len(profiles)} saved)\n\n"
            "Select a profile below to Run Now, Edit, Pause/Resume, Duplicate, Delete, or View Results:"
        )
    kb = _build_profiles_list_keyboard(profiles)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text=text, reply_markup=kb)
    elif update.effective_message:
        await update.effective_message.reply_text(text=text, reply_markup=kb)


@require_auth
async def search_action_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle profile management actions: view, run, pause, resume, dup, delask, delconfirm."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    user_id, tg_id = _ensure_user_and_settings(update, context)
    db: DatabaseManager = context.application.bot_data["db"]
    parts = query.data.split(":")
    action = parts[1]

    if action == "list":
        await searches_command(update, context)
        return

    profile_id = int(parts[2])

    with db.session() as session:
        repo = SearchProfileRepository(session)
        profile = repo.get_profile(profile_id, user_id=user_id)
        if profile is None:
            await query.answer("⚠️ Search profile not found or access denied.", show_alert=True)
            return

        if action == "view":
            await query.answer()
            status_str = "🟢 Active" if profile.is_active else "⏸️ Paused"
            text = (
                f"📌 **Profile #{profile.id}** — {status_str}\n\n"
                f"{profile.filters.format_summary(profile.name)}"
            )
            await query.edit_message_text(
                text=text,
                reply_markup=_build_profile_detail_keyboard(profile),
            )
            return

        if action == "pause":
            updated = repo.update_profile(profile_id, user_id, is_active=False)
            assert updated is not None
            await query.answer("⏸️ Search paused")
            text = (
                f"📌 **Profile #{updated.id}** — ⏸️ Paused\n\n"
                f"{updated.filters.format_summary(updated.name)}"
            )
            await query.edit_message_text(
                text=text,
                reply_markup=_build_profile_detail_keyboard(updated),
            )
            return

        if action == "resume":
            updated = repo.update_profile(profile_id, user_id, is_active=True)
            assert updated is not None
            await query.answer("▶️ Search resumed")
            text = (
                f"📌 **Profile #{updated.id}** — 🟢 Active\n\n"
                f"{updated.filters.format_summary(updated.name)}"
            )
            await query.edit_message_text(
                text=text,
                reply_markup=_build_profile_detail_keyboard(updated),
            )
            return

        if action == "dup":
            dup = repo.duplicate_profile(profile_id, user_id)
            assert dup is not None
            await query.answer("📋 Profile duplicated!")
            text = (
                f"✅ **Duplicated Profile #{dup.id}** — 🟢 Active\n\n"
                f"{dup.filters.format_summary(dup.name)}"
            )
            await query.edit_message_text(
                text=text,
                reply_markup=_build_profile_detail_keyboard(dup),
            )
            return

        if action == "delask":
            await query.answer()
            confirm_kb = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🗑️ Yes, Delete Permanently",
                            callback_data=f"srch:delconfirm:{profile_id}",
                        )
                    ],
                    [InlineKeyboardButton("⬅️ Cancel", callback_data=f"srch:view:{profile_id}")],
                ]
            )
            await query.edit_message_text(
                f"⚠️ Are you sure you want to delete **{profile.name}**?\n\n"
                "Historical listings and evaluations will remain safely in the database.",
                reply_markup=confirm_kb,
            )
            return

        if action == "delconfirm":
            repo.delete_profile(profile_id, user_id)
            await query.answer("🗑️ Profile deleted")

    if action == "delconfirm":
        await searches_command(update, context)
        return

    if action == "run":
        allowed, wait_s = check_rate_limit(tg_id, cooldown_seconds=5.0)
        if not allowed:
            await query.answer(f"⏳ Please wait {wait_s}s before running again.", show_alert=True)
            return
        search_service = context.application.bot_data.get("search_service")
        if search_service is not None:
            await query.answer("🚀 Running search...")
            summary_msg = await search_service.run_single_profile_scan(
                profile_id=profile_id,
                user_id=user_id,
                telegram_user_id=tg_id,
                bot=context.bot,
            )
            await query.edit_message_text(
                summary_msg,
                reply_markup=_build_profile_detail_keyboard(profile),
            )
        else:
            await query.answer("✅ Profile queued for scan!")
            await query.edit_message_text(
                f"🚀 Executed scan check for **{profile.name}**.\n\n"
                f"{profile.filters.format_summary(profile.name)}",
                reply_markup=_build_profile_detail_keyboard(profile),
            )


@require_auth
async def natural_language_message_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Parse free-text messages outside the wizard as natural language search queries."""
    if update.effective_message is None or not update.effective_message.text:
        return
    user_id, _ = _ensure_user_and_settings(update, context)
    db: DatabaseManager = context.application.bot_data["db"]
    with db.session() as session:
        user_repo = UserRepository(session)
        user = user_repo.get_by_telegram_id(update.effective_user.id)  # type: ignore[union-attr]
        max_price = user.settings.default_max_price_usd if user and user.settings else 5000
        min_profit = user.settings.default_min_profit_usd if user and user.settings else 500
        min_score = user.settings.default_min_score if user and user.settings else 70

    parsed = parse_natural_language_search(
        update.effective_message.text,
        default_max_price_usd=max_price,
        default_min_profit_usd=min_profit,
        default_min_score=min_score,
    )

    if not parsed.is_confident:
        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔎 Launch Search Wizard", callback_data=CB_MENU_CREATE_SEARCH
                    )
                ],
                [InlineKeyboardButton("🏠 Main Menu", callback_data=CB_MAIN_MENU)],
            ]
        )
        await update.effective_message.reply_text(
            "🤔 I couldn't confidently recognize specific vehicle filters from that message.\n\n"
            "Try an example like:\n"
            "• `Find Toyota Prius under $4000`\n"
            "• `Electric cars under $5000`\n"
            "• `BMW coupe 2012-2018`\n"
            "• `Find 4x4 under $3000`\n\n"
            "Or tap **Launch Search Wizard** below to configure step-by-step:",
            reply_markup=kb,
        )
        return

    if context.user_data is not None:
        context.user_data["nl_draft"] = {
            "name": parsed.suggested_name,
            "filters": parsed.filters.model_dump(mode="json"),
        }

    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Save and Activate", callback_data="nl:save"),
                InlineKeyboardButton("❌ Cancel", callback_data=CB_CANCEL),
            ]
        ]
    )
    await update.effective_message.reply_text(
        "🤖 **Natural Language Search Draft**\n\n"
        f"{parsed.filters.format_summary(parsed.suggested_name)}\n\n"
        "Would you like to save and activate this search?",
        reply_markup=kb,
    )


@require_auth
async def natural_language_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Confirm and save a natural language search draft."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    user_id, _ = _ensure_user_and_settings(update, context)
    nl_draft = (context.user_data or {}).get("nl_draft")
    if not nl_draft:
        await query.answer("⚠️ Draft expired. Please send your search text again.", show_alert=True)
        return

    cfg = SearchFilterConfig.model_validate(nl_draft["filters"])
    name = nl_draft["name"]
    db: DatabaseManager = context.application.bot_data["db"]
    with db.session() as session:
        repo = SearchProfileRepository(session)
        saved = repo.create_profile(user_id=user_id, name=name, filters=cfg, is_active=True)

    if context.user_data is not None:
        context.user_data.pop("nl_draft", None)

    await query.answer("✅ Search saved and activated!")
    await query.edit_message_text(
        f"✅ **Saved Search #{saved.id}!**\n\n{cfg.format_summary(name)}",
        reply_markup=build_main_menu_keyboard(),
    )


def register_search_handlers(app: Application[Any, Any, Any, Any, Any, Any]) -> None:
    """Register search wizard, /searches management, and natural language handlers on Application."""
    app.bot_data["searches_command_handler"] = searches_command
    app.add_handler(build_search_wizard_conversation_handler(), group=0)
    app.add_handler(CommandHandler("searches", searches_command), group=0)
    app.add_handler(
        CallbackQueryHandler(
            search_action_callback_handler,
            pattern=r"^srch:(list|view|run|pause|resume|dup|delask|delconfirm):",
        ),
        group=0,
    )
    app.add_handler(
        CallbackQueryHandler(search_action_callback_handler, pattern=r"^srch:list$"),
        group=0,
    )
    app.add_handler(
        CallbackQueryHandler(natural_language_callback_handler, pattern=r"^nl:save$"),
        group=0,
    )
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, natural_language_message_handler),
        group=1,
    )
