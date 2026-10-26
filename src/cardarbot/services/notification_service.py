from __future__ import annotations

import asyncio
import logging
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from cardarbot.database.models import ListingModel, UserSettingsModel
from cardarbot.database.repositories import DealRepository
from cardarbot.database.session import DatabaseManager
from cardarbot.domain.deals import DealEvaluationDomain

logger = logging.getLogger("cardarbot.services.notification")


def format_deal_notification_message(
    listing: ListingModel,
    evaluation: DealEvaluationDomain,
    alert_type: str = "new_deal",
) -> str:
    """Format a qualifying car flip opportunity into the required Telegram notification card."""
    header = (
        "💎 POTENTIAL CAR FLIP"
        if alert_type == "new_deal"
        else "📉 PRICE DROP — POTENTIAL CAR FLIP"
    )
    title_parts = [p for p in (listing.make, listing.model, str(listing.year or "")) if p]
    vehicle_title = (
        " ".join(title_parts) if title_parts else f"Listing #{listing.source_listing_id}"
    )
    location = listing.location or "Tbilisi"

    asking = evaluation.profit.asking_price_usd
    resale = evaluation.profit.conservative_resale_usd
    expenses = evaluation.profit.total_expenses_usd
    net_profit = evaluation.profit.net_profit_usd
    score = evaluation.score.total_score
    profile_name = evaluation.matched_profile_name or "General Scan"

    resale_str = f"${resale:,.0f}" if resale is not None else "Uncertain"
    profit_str = f"${net_profit:,.0f}" if net_profit is not None else "Uncertain"

    reasons_lines = (
        "\n".join(f"- {r}" for r in evaluation.score.reasons[:4])
        if evaluation.score.reasons
        else "- Matched search filters"
    )
    risks_lines = (
        "\n".join(f"- {rk}" for rk in evaluation.score.risks[:4])
        if evaluation.score.risks
        else "- Mechanical condition unverified\n- Inspection required"
    )

    return (
        f"{header}\n\n"
        f"🚗 {vehicle_title}\n"
        f"📍 {location}\n\n"
        f"💰 Asking price: ${asking:,.0f}\n"
        f"📊 Conservative resale: {resale_str}\n"
        f"🔧 Estimated expenses: ${expenses:,.0f}\n\n"
        f"💵 Estimated net profit: {profit_str}\n\n"
        f"⭐ Score: {score}/100\n\n"
        f"Matched search:\n{profile_name}\n\n"
        f"Reasons:\n{reasons_lines}\n\n"
        f"Risks:\n{risks_lines}\n\n"
        f"🔗 View on MyAuto: {listing.url}"
    )


def build_deal_notification_keyboard(listing_id: int, url: str) -> InlineKeyboardMarkup:
    """Build inline action buttons for a deal notification or deal card."""
    keyboard = [
        [
            InlineKeyboardButton("🔎 Details", callback_data=f"deal:detail:{listing_id}"),
            InlineKeyboardButton("📊 Comparables", callback_data=f"deal:comps:{listing_id}"),
        ],
        [
            InlineKeyboardButton("⭐ Save", callback_data=f"deal:save:{listing_id}"),
            InlineKeyboardButton("❌ Dismiss", callback_data=f"deal:dismiss:{listing_id}"),
        ],
        [
            InlineKeyboardButton("📈 Price History", callback_data=f"deal:history:{listing_id}"),
            InlineKeyboardButton("🔗 View on MyAuto", url=url),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


class NotificationService:
    """Handles deduplicated Telegram deal alert delivery with retry logic and alert limits."""

    def __init__(self, db: DatabaseManager, max_retries: int = 2) -> None:
        self.db = db
        self.max_retries = max_retries

    async def notify_if_qualifying(
        self,
        bot: Any,
        user_id: int,
        telegram_user_id: int,
        user_settings: UserSettingsModel | None,
        listing: ListingModel,
        evaluation: DealEvaluationDomain,
        min_score_threshold: int = 70,
        min_profit_threshold_usd: float = 500.0,
    ) -> bool:
        """Send a Telegram alert if the deal qualifies and has not already been notified."""
        if user_settings is not None and not user_settings.notifications_enabled:
            return False

        if evaluation.score.hard_rejected or evaluation.valuation.is_uncertain:
            return False

        if evaluation.score.total_score < min_score_threshold:
            return False

        if (
            evaluation.profit.net_profit_usd is None
            or evaluation.profit.net_profit_usd < min_profit_threshold_usd
        ):
            return False

        with self.db.session() as session:
            deal_repo = DealRepository(session)
            dismissed_ids = set(deal_repo.list_dismissed_listing_ids(user_id))
            if listing.id in dismissed_ids:
                return False

            already_notified, alert_type = deal_repo.was_recently_notified(
                user_id=user_id,
                listing_id=listing.id,
                current_price_usd=evaluation.profit.asking_price_usd,
            )
            if already_notified:
                return False

            text = format_deal_notification_message(
                listing=listing,
                evaluation=evaluation,
                alert_type=alert_type,
            )
            kb = build_deal_notification_keyboard(listing.id, listing.url)

        # Deliver via Telegram bot with retries
        retries = 0
        delivered = False
        if bot is not None:
            while retries <= self.max_retries:
                try:
                    await bot.send_message(
                        chat_id=telegram_user_id,
                        text=text,
                        reply_markup=kb,
                    )
                    delivered = True
                    break
                except Exception as exc:
                    retries += 1
                    logger.warning(
                        "Telegram alert delivery attempt %d failed for user %d: %s",
                        retries,
                        telegram_user_id,
                        exc,
                    )
                    if retries <= self.max_retries:
                        await asyncio.sleep(0.2 * retries)
        else:
            # Dry-run or headless CLI mode records notification without live bot instance
            delivered = True

        with self.db.session() as session:
            deal_repo = DealRepository(session)
            deal_repo.record_notification(
                user_id=user_id,
                listing_id=listing.id,
                notified_price_usd=evaluation.profit.asking_price_usd,
                score=evaluation.score.total_score,
                profile_id=evaluation.matched_profile_id,
                alert_type=alert_type,
                delivery_status="sent" if delivered else "failed",
                retry_count=retries,
            )
        return delivered
