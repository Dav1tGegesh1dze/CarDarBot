from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from cardarbot.bot.auth import require_auth
from cardarbot.bot.callbacks import CB_MAIN_MENU
from cardarbot.bot.handlers.core import _ensure_user_and_settings
from cardarbot.bot.keyboards import build_back_to_main_keyboard
from cardarbot.database.models import DealEvaluationModel, ListingModel
from cardarbot.database.repositories import (
    DealRepository,
    ListingRepository,
    SearchProfileRepository,
)
from cardarbot.database.session import DatabaseManager
from cardarbot.services.deal_service import (
    DealService,
    does_listing_match_filter,
    listing_model_to_domain,
)
from cardarbot.sources.import_adapter import ListingImportAdapter
from cardarbot.utils.logging import format_tbilisi_time

logger = logging.getLogger("cardarbot.handlers.deals")

PAGE_SIZE = 5


def _build_deals_menu_keyboard(
    current_mode: str = "score",
    page: int = 0,
    total_count: int = 0,
    listing_rows: list[tuple[ListingModel, DealEvaluationModel | None]] | None = None,
    profile_id: int | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("⭐ Best Scores", callback_data="deal:browse:score:0"),
            InlineKeyboardButton("💵 Highest Profit", callback_data="deal:browse:profit:0"),
        ],
        [
            InlineKeyboardButton("🕒 Latest Deals", callback_data="deal:browse:latest:0"),
            InlineKeyboardButton("🏷️ Cheapest", callback_data="deal:browse:cheapest:0"),
        ],
        [
            InlineKeyboardButton("⭐ Saved Vehicles", callback_data="deal:browse:saved:0"),
            InlineKeyboardButton("🗑️ Dismissed", callback_data="deal:browse:dismissed:0"),
        ],
    ]

    if listing_rows:
        for l_row, ev_row in listing_rows:
            score_tag = f"[{ev_row.score}/100] " if ev_row else ""
            profit_tag = (
                f"(+${ev_row.net_profit_usd:,.0f})"
                if ev_row and ev_row.net_profit_usd is not None
                else ""
            )
            label = (
                f"{score_tag}{l_row.make or ''} {l_row.model or ''} "
                f"{l_row.year or ''} — ${(l_row.usd_price or 0):,.0f} {profit_tag}"
            ).strip()
            rows.append([InlineKeyboardButton(label[:60], callback_data=f"deal:detail:{l_row.id}")])

    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        prev_cb = (
            f"deal:profile:{profile_id}:{page - 1}"
            if profile_id is not None
            else f"deal:browse:{current_mode}:{page - 1}"
        )
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=prev_cb))
    if (page + 1) * PAGE_SIZE < total_count:
        next_cb = (
            f"deal:profile:{profile_id}:{page + 1}"
            if profile_id is not None
            else f"deal:browse:{current_mode}:{page + 1}"
        )
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=next_cb))
    if nav_row:
        rows.append(nav_row)

    rows.append([InlineKeyboardButton("🏠 Main Menu", callback_data=CB_MAIN_MENU)])
    return InlineKeyboardMarkup(rows)


def _query_deals_for_mode(
    db: DatabaseManager,
    user_id: int,
    mode: str,
    page: int = 0,
    profile_id: int | None = None,
) -> tuple[list[tuple[ListingModel, DealEvaluationModel | None]], int]:
    """Query clean listings and their latest evaluations according to the requested browse mode."""
    with db.session() as session:
        d_repo = DealRepository(session)
        p_repo = SearchProfileRepository(session)
        saved_ids = set(d_repo.list_saved_listing_ids(user_id))
        dismissed_ids = set(d_repo.list_dismissed_listing_ids(user_id))

        target_profile = (
            p_repo.get_profile(profile_id, user_id=user_id) if profile_id is not None else None
        )
        if profile_id is not None and target_profile is None:
            return [], 0

        active_profiles = (
            [p for p in p_repo.list_user_profiles(user_id) if p.is_active]
            if profile_id is None and mode not in {"saved", "dismissed"}
            else []
        )

        stmt = select(ListingModel).where(ListingModel.is_spam_or_rejected.is_(False))
        all_listings = list(session.execute(stmt).scalars().all())

        paired: list[tuple[ListingModel, DealEvaluationModel | None]] = []
        for l_row in all_listings:
            if mode == "saved" and l_row.id not in saved_ids:
                continue
            if mode == "dismissed" and l_row.id not in dismissed_ids:
                continue
            if mode not in {"saved", "dismissed"} and l_row.id in dismissed_ids:
                continue

            ev_row, _ = d_repo.get_latest_evaluation(l_row.id)
            if mode not in {"saved", "dismissed"} and ev_row is not None and ev_row.hard_rejected:
                continue

            domain_listing = listing_model_to_domain(l_row)

            if target_profile is not None:
                if not does_listing_match_filter(domain_listing, target_profile.filters):
                    continue
            elif active_profiles and not any(
                does_listing_match_filter(domain_listing, p.filters) for p in active_profiles
            ):
                continue

            paired.append((l_row, ev_row))

        if mode == "score":
            paired.sort(
                key=lambda x: (
                    x[1].score if x[1] else -1,
                    (x[1].net_profit_usd or -99999) if x[1] else -99999,
                ),
                reverse=True,
            )
        elif mode == "profit":
            paired.sort(
                key=lambda x: (x[1].net_profit_usd or -99999) if x[1] else -99999, reverse=True
            )
        elif mode == "cheapest":
            paired.sort(key=lambda x: x[0].usd_price if x[0].usd_price is not None else 999999)
        else:  # latest, saved, dismissed
            paired.sort(key=lambda x: x[0].id, reverse=True)

        total = len(paired)
        start = page * PAGE_SIZE
        end = start + PAGE_SIZE
        return paired[start:end], total


@require_auth
async def deals_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /deals and 💎 Best Deals button."""
    user_id, _ = _ensure_user_and_settings(update, context)
    db: DatabaseManager = context.application.bot_data["db"]
    items, total = _query_deals_for_mode(db, user_id, mode="score", page=0)

    if total == 0:
        text = (
            "💎 **Deal Browser (Best Scores)**\n\n"
            "No evaluated deals found yet.\n"
            "• Create a search profile with /newsearch and run `/scan`\n"
            "• Or upload a `.json` / `.csv` / `.html` listings file directly in chat to import & evaluate!"
        )
    else:
        text = (
            f"💎 **Deal Browser — Best Scores** (Showing {len(items)} of {total})\n\n"
            "Select a vehicle below to inspect valuation details, comparables, and price history:"
        )
    kb = _build_deals_menu_keyboard("score", 0, total, items)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text=text, reply_markup=kb)
    elif update.effective_message:
        await update.effective_message.reply_text(text=text, reply_markup=kb)


@require_auth
async def saved_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /saved and ⭐ Saved Cars button."""
    user_id, _ = _ensure_user_and_settings(update, context)
    db: DatabaseManager = context.application.bot_data["db"]
    items, total = _query_deals_for_mode(db, user_id, mode="saved", page=0)

    if total == 0:
        text = "⭐ **Saved Cars**\n\nYou haven't saved any vehicles yet. Tap **⭐ Save** on any deal card to bookmark it."
    else:
        text = f"⭐ **Saved Cars** ({total} saved)\n\nSelect a saved vehicle below:"
    kb = _build_deals_menu_keyboard("saved", 0, total, items)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text=text, reply_markup=kb)
    elif update.effective_message:
        await update.effective_message.reply_text(text=text, reply_markup=kb)


@require_auth
async def deal_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle deal browsing, pagination, detail view, comparables, price history, save, and dismiss."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    user_id, _ = _ensure_user_and_settings(update, context)
    db: DatabaseManager = context.application.bot_data["db"]
    parts = query.data.split(":")
    action = parts[1]

    if action == "browse":
        mode = parts[2]
        page = int(parts[3])
        items, total = _query_deals_for_mode(db, user_id, mode=mode, page=page)
        mode_titles = {
            "score": "Best Scores",
            "profit": "Highest Estimated Profit",
            "latest": "Latest Deals",
            "cheapest": "Cheapest Vehicles",
            "saved": "Saved Vehicles",
            "dismissed": "Dismissed Vehicles",
        }
        title = mode_titles.get(mode, mode.title())
        text = f"💎 **Deal Browser — {title}** (Page {page + 1}, Total: {total})\n\n" + (
            "Select a listing below:" if items else "No vehicles in this view."
        )
        await query.answer()
        await query.edit_message_text(
            text=text,
            reply_markup=_build_deals_menu_keyboard(mode, page, total, items),
        )
        return

    if action == "profile":
        profile_id = int(parts[2])
        page = int(parts[3])
        with db.session() as session:
            p_repo = SearchProfileRepository(session)
            prof = p_repo.get_profile(profile_id, user_id=user_id)
        prof_title = prof.name if prof else f"Profile #{profile_id}"
        items, total = _query_deals_for_mode(
            db, user_id, mode="score", page=page, profile_id=profile_id
        )
        text = f"💎 **Results for {prof_title}** (Page {page + 1}, Matching: {total})\n\n" + (
            "Select a listing below:"
            if items
            else "No matching vehicles found for this search filter yet. Tap **▶️ Run Now** on the search profile to scan!"
        )
        await query.answer()
        await query.edit_message_text(
            text=text,
            reply_markup=_build_deals_menu_keyboard(
                "score", page, total, items, profile_id=profile_id
            ),
        )
        return

    listing_id = int(parts[2])

    with db.session() as session:
        l_repo = ListingRepository(session)
        d_repo = DealRepository(session)
        listing = l_repo.get_by_id(listing_id)
        if listing is None:
            await query.answer("⚠️ Listing not found.", show_alert=True)
            return

        if action == "save":
            d_repo.save_deal_for_user(user_id=user_id, listing_id=listing_id)
            await query.answer("⭐ Saved to your Saved Cars!")
            return

        if action == "dismiss":
            d_repo.dismiss_deal_for_user(user_id=user_id, listing_id=listing_id)
            await query.answer("❌ Listing dismissed.")
            await query.edit_message_text(
                f"❌ Dismissed **{listing.make or ''} {listing.model or ''} ({listing.year or ''})**.",
                reply_markup=build_back_to_main_keyboard(),
            )
            return

        ev_row, comp_row = d_repo.get_latest_evaluation(listing_id)
        history = l_repo.get_price_history(listing_id)

        detail_kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🔎 Details", callback_data=f"deal:detail:{listing_id}"),
                    InlineKeyboardButton(
                        "📊 Comparables", callback_data=f"deal:comps:{listing_id}"
                    ),
                    InlineKeyboardButton("📈 History", callback_data=f"deal:history:{listing_id}"),
                ],
                [
                    InlineKeyboardButton("⭐ Save", callback_data=f"deal:save:{listing_id}"),
                    InlineKeyboardButton("❌ Dismiss", callback_data=f"deal:dismiss:{listing_id}"),
                ],
                [
                    InlineKeyboardButton("🔗 Open on MyAuto", url=listing.url),
                    InlineKeyboardButton("⬅️ Back to Deals", callback_data="deal:browse:score:0"),
                ],
            ]
        )

        if action == "detail":
            await query.answer()
            resale_str = (
                f"${ev_row.conservative_resale_usd:,.0f}"
                if ev_row and ev_row.conservative_resale_usd is not None
                else "Uncertain"
            )
            profit_str = (
                f"${ev_row.net_profit_usd:,.0f} ({ev_row.return_percentage or 0:.1f}% ROI)"
                if ev_row and ev_row.net_profit_usd is not None
                else "Uncertain"
            )
            score_str = f"{ev_row.score}/100 ({ev_row.classification.upper()})" if ev_row else "N/A"
            reasons = (
                "\n".join(f"• {r}" for r in (ev_row.reasons_json if ev_row else [])) or "• None"
            )
            risks = (
                "\n".join(f"• {r}" for r in (ev_row.risks_json if ev_row else []))
                or "• Inspection required"
            )

            text = (
                f"🔎 **Vehicle Evaluation Details**\n\n"
                f"🚗 **{listing.make or 'Unknown'} {listing.model or ''} {listing.year or ''}**\n"
                f"📍 Location: {listing.location or 'Tbilisi'} | Customs: {listing.customs_status}\n"
                f"⛽ Fuel: {listing.fuel} | 🕹️ Trans: {listing.transmission} | ⚙️ Drive: {listing.drivetrain}\n"
                f"🛣️ Mileage: {f'{listing.mileage_km:,} km' if listing.mileage_km else 'Unknown'}\n\n"
                f"💰 Asking Price: **${(listing.usd_price or 0):,.0f}**\n"
                f"📊 Conservative Resale: **{resale_str}**\n"
                f"🔧 Est. Expenses: **${(ev_row.expenses_usd if ev_row else 400):,.0f}**\n"
                f"💵 Est. Net Profit: **{profit_str}**\n"
                f"⭐ Deal Score: **{score_str}**\n\n"
                f"**Reasons:**\n{reasons}\n\n"
                f"**Risks:**\n{risks}"
            )
            await query.edit_message_text(text=text, reply_markup=detail_kb)
            return

        if action == "comps":
            await query.answer()
            if comp_row is None or not comp_row.comparables_json:
                text = (
                    f"📊 **Comparable Vehicles for {listing.make} {listing.model}**\n\n"
                    "No comparable listings recorded for this snapshot."
                )
            else:
                lines = [
                    f"• #{c.get('source_listing_id')}: {c.get('year') or ''} — "
                    f"${c.get('usd_price', 0):,.0f} ({c.get('mileage_km') or '?'} km)"
                    for c in comp_row.comparables_json[:8]
                ]
                text = (
                    f"📊 **Comparable Vehicles ({comp_row.comparable_count} matched)**\n\n"
                    f"• Median Asking: ${(comp_row.median_asking_usd or 0):,.0f}\n"
                    f"• 25th Percentile: ${(comp_row.q25_asking_usd or 0):,.0f}\n"
                    f"• Resale Discount Applied: {comp_row.resale_discount_percent:.0f}%\n"
                    f"• Conservative Resale: **${(comp_row.conservative_resale_usd or 0):,.0f}**\n"
                    f"• Confidence: `{comp_row.confidence}`\n\n"
                    "**Matched Listings:**\n" + "\n".join(lines)
                )
            await query.edit_message_text(text=text, reply_markup=detail_kb)
            return

        if action == "history":
            await query.answer()
            if not history:
                text = "📈 **Price History**\n\nNo price history entries recorded."
            else:
                h_lines = []
                for h in history:
                    ts = format_tbilisi_time(h.recorded_at)
                    if h.old_usd_price is None:
                        h_lines.append(f"• {ts}: Initial price **${h.new_usd_price:,.0f}**")
                    else:
                        h_lines.append(
                            f"• {ts}: ${h.old_usd_price:,.0f} ➡️ **${h.new_usd_price:,.0f}** "
                            f"({h.price_change_usd or 0:+.0f} USD)"
                        )
                text = f"📈 **Price History — {listing.make} {listing.model}**\n\n" + "\n".join(
                    h_lines
                )
            await query.edit_message_text(text=text, reply_markup=detail_kb)


@require_auth
async def document_import_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Allow authorized users to upload a .json, .csv, or .html export file directly in Telegram."""
    if update.effective_message is None or update.effective_message.document is None:
        return
    _ensure_user_and_settings(update, context)
    doc = update.effective_message.document
    file_name = (doc.file_name or "").lower()
    if not file_name.endswith((".json", ".csv", ".html", ".htm")):
        await update.effective_message.reply_text(
            "⚠️ Unsupported file type. Please upload a `.json`, `.csv`, or `.html` listings export."
        )
        return

    tg_file = await doc.get_file()
    raw_bytes = await tg_file.download_as_bytearray()
    content = raw_bytes.decode("utf-8", errors="replace")

    settings = context.application.bot_data["settings"]
    db: DatabaseManager = context.application.bot_data["db"]
    adapter = ListingImportAdapter(
        gel_to_usd_rate=settings.gel_to_usd_rate,
        eur_to_usd_rate=settings.eur_to_usd_rate,
    )
    if file_name.endswith(".json"):
        listings = adapter.parse_json_content(content)
    elif file_name.endswith(".csv"):
        listings = adapter.parse_csv_content(content)
    else:
        listings = adapter.parse_html_content(content)

    deal_service = DealService(db=db, settings=settings)
    evaluated = deal_service.ingest_and_evaluate_listings(listings)
    qualifying = sum(
        1
        for _, ev in evaluated
        if ev.score.total_score >= settings.default_min_deal_score and not ev.score.hard_rejected
    )

    await update.effective_message.reply_text(
        f"📥 **Import Complete (`{doc.file_name}`)**\n\n"
        f"• Listings Imported & Evaluated: {len(evaluated)}\n"
        f"• Strong/Exceptional Deals (≥{settings.default_min_deal_score}): {qualifying}\n\n"
        "Use /deals to browse evaluated vehicles or /scan to match against your active searches!",
        reply_markup=build_back_to_main_keyboard(),
    )


def register_deal_handlers(app: Application[Any, Any, Any, Any, Any, Any]) -> None:
    """Register /deals, /saved, deal callbacks, and document import handlers."""
    settings = app.bot_data["settings"]
    db = app.bot_data["db"]
    from cardarbot.services.search_service import SearchService

    if "search_service" not in app.bot_data:
        app.bot_data["search_service"] = SearchService(db=db, settings=settings)

    app.bot_data["deals_command_handler"] = deals_command
    app.bot_data["saved_command_handler"] = saved_command

    app.add_handler(CommandHandler("deals", deals_command), group=0)
    app.add_handler(CommandHandler("saved", saved_command), group=0)
    app.add_handler(CallbackQueryHandler(deal_callback_handler, pattern=r"^deal:"), group=0)
    app.add_handler(MessageHandler(filters.Document.ALL, document_import_handler), group=0)
