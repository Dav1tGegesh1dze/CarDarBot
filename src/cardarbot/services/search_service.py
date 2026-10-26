from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from cardarbot.config import Settings
from cardarbot.database.models import UserModel
from cardarbot.database.repositories import (
    DealRepository,
    ListingRepository,
    SearchProfileRepository,
    UserRepository,
)
from cardarbot.database.session import DatabaseManager
from cardarbot.domain.search_profiles import SearchProfileDomain
from cardarbot.services.deal_service import (
    DealService,
    does_listing_match_filter,
    listing_model_to_domain,
)
from cardarbot.services.notification_service import NotificationService
from cardarbot.sources.base import BaseListingSource
from cardarbot.sources.myauto import MyAutoSource

logger = logging.getLogger("cardarbot.services.search")


class SearchService:
    """Orchestrates manual and scheduled profile scans, source health tracking, and deal notifications."""

    def __init__(
        self,
        db: DatabaseManager,
        settings: Settings,
        source: BaseListingSource | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.source = source or MyAutoSource(
            gel_to_usd_rate=settings.gel_to_usd_rate,
            eur_to_usd_rate=settings.eur_to_usd_rate,
        )
        self.deal_service = DealService(db=db, settings=settings)
        self.notification_service = NotificationService(db=db)

    async def execute_profile_scan(
        self,
        profile: SearchProfileDomain,
        telegram_user_id: int,
        bot: Any = None,
        trigger_type: str = "scheduled",
    ) -> dict[str, Any]:
        """Run a scan for a single search profile, evaluate candidates, and send alerts."""
        with self.db.session() as session:
            d_repo = DealRepository(session)
            job = d_repo.create_scan_job(profile_id=profile.id, trigger_type=trigger_type)
            job_id = job.id

        fetch_res = await self.source.fetch_listings(filters=profile.filters)

        with self.db.session() as session:
            d_repo = DealRepository(session)
            d_repo.update_source_health(
                source_name=fetch_res.source_name,
                status_mode=fetch_res.status_mode.value,
                error_message=fetch_res.error_message,
                details=fetch_res.metadata,
            )

        # If live source returned listings, ingest and evaluate them;
        # otherwise evaluate existing clean database listings matching this profile
        candidates = fetch_res.listings
        if not candidates:
            with self.db.session() as session:
                l_repo = ListingRepository(session)
                db_rows = l_repo.list_clean_listings()
                all_domain = [listing_model_to_domain(r) for r in db_rows]
                candidates = [
                    c for c in all_domain if does_listing_match_filter(c, profile.filters)
                ]

        evaluated = self.deal_service.ingest_and_evaluate_listings(
            listings=candidates,
            profile=profile,
        )

        deals_found = 0
        alerts_sent = 0
        matching_candidates = 0
        max_alerts = self.settings.max_alerts_per_scan

        with self.db.session() as session:
            u_repo = UserRepository(session)
            user = u_repo.get_by_telegram_id(telegram_user_id)
            user_settings = user.settings if user else None
            if user_settings:
                max_alerts = user_settings.max_alerts_per_scan

        for listing_row, eval_domain in evaluated:
            if listing_row.is_spam_or_rejected or eval_domain.score.hard_rejected:
                continue
            norm_cand = listing_model_to_domain(listing_row)
            if not does_listing_match_filter(norm_cand, profile.filters):
                continue
            matching_candidates += 1
            if (
                eval_domain.score.total_score >= profile.filters.min_deal_score
                and (eval_domain.profit.net_profit_usd or 0.0) >= profile.filters.min_profit_usd
            ):
                deals_found += 1
                if alerts_sent < max_alerts:
                    sent = await self.notification_service.notify_if_qualifying(
                        bot=bot,
                        user_id=profile.user_id,
                        telegram_user_id=telegram_user_id,
                        user_settings=user_settings,
                        listing=listing_row,
                        evaluation=eval_domain,
                        min_score_threshold=profile.filters.min_deal_score,
                        min_profit_threshold_usd=float(profile.filters.min_profit_usd),
                    )
                    if sent:
                        alerts_sent += 1

        with self.db.session() as session:
            p_repo = SearchProfileRepository(session)
            d_repo = DealRepository(session)
            if profile.id is not None:
                p_repo.mark_scanned(profile.id)
            d_repo.finish_scan_job(
                job_id=job_id,
                status="completed",
                listings_fetched=matching_candidates,
                deals_found=deals_found,
                alerts_sent=alerts_sent,
                error_message=fetch_res.error_message,
            )

        return {
            "profile_name": profile.name,
            "source_mode": fetch_res.status_mode.value,
            "candidates_evaluated": matching_candidates,
            "deals_found": deals_found,
            "alerts_sent": alerts_sent,
            "source_note": fetch_res.error_message,
        }

    async def run_single_profile_scan(
        self,
        profile_id: int,
        user_id: int,
        telegram_user_id: int,
        bot: Any = None,
    ) -> str:
        with self.db.session() as session:
            p_repo = SearchProfileRepository(session)
            profile = p_repo.get_profile(profile_id, user_id=user_id)
        if profile is None:
            return "⚠️ Search profile not found."

        stats = await self.execute_profile_scan(
            profile=profile,
            telegram_user_id=telegram_user_id,
            bot=bot,
            trigger_type="manual",
        )
        return (
            f"✅ **Scan Completed: {stats['profile_name']}**\n\n"
            f"• Source Mode: `{stats['source_mode']}`\n"
            f"• Listings Evaluated: {stats['candidates_evaluated']}\n"
            f"• Qualifying Deals Found: {stats['deals_found']}\n"
            f"• New Alerts Sent: {stats['alerts_sent']}"
        )

    async def run_manual_scan_for_user(
        self,
        user_id: int,
        telegram_user_id: int,
        bot: Any = None,
    ) -> str:
        with self.db.session() as session:
            p_repo = SearchProfileRepository(session)
            profiles = [p for p in p_repo.list_user_profiles(user_id) if p.is_active]

        if not profiles:
            return (
                "ℹ️ You have no active search profiles to scan.\nCreate one first with /newsearch!"
            )

        total_eval = 0
        total_deals = 0
        total_alerts = 0
        last_mode = "import_only"
        for p in profiles:
            st = await self.execute_profile_scan(
                profile=p,
                telegram_user_id=telegram_user_id,
                bot=bot,
                trigger_type="manual",
            )
            total_eval += st["candidates_evaluated"]
            total_deals += st["deals_found"]
            total_alerts += st["alerts_sent"]
            last_mode = st["source_mode"]

        return (
            f"✅ **Manual Scan Complete ({len(profiles)} active profiles)**\n\n"
            f"• Source Mode: `{last_mode}`\n"
            f"• Total Candidates Evaluated: {total_eval}\n"
            f"• Qualifying Deals Found: {total_deals}\n"
            f"• New Alerts Sent: {total_alerts}\n\n"
            "Use /deals to browse all evaluated opportunities."
        )

    async def run_all_active_profiles_scheduled(self, bot: Any = None) -> int:
        """Execute scheduled scans for all active profiles across authorized users."""
        with self.db.session() as session:
            p_repo = SearchProfileRepository(session)
            profiles = p_repo.list_all_active_profiles()
            user_map: dict[int, int] = {}
            for u in session.execute(select(UserModel)).scalars().all():
                user_map[u.id] = u.telegram_user_id

        count = 0
        for p in profiles:
            tg_id = user_map.get(p.user_id)
            if tg_id is None:
                continue
            await self.execute_profile_scan(
                profile=p,
                telegram_user_id=tg_id,
                bot=bot,
                trigger_type="scheduled",
            )
            count += 1
        return count
