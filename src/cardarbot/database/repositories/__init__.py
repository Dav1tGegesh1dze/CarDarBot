from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from cardarbot.database.models import (
    ComparableSnapshotModel,
    DealEvaluationModel,
    DismissedDealModel,
    ListingModel,
    ListingObservationModel,
    NotificationModel,
    PriceHistoryModel,
    SavedDealModel,
    ScanJobModel,
    SearchFilterModel,
    SearchProfileModel,
    SourceHealthModel,
    UserModel,
    UserSettingsModel,
)
from cardarbot.domain.deals import DealEvaluationDomain
from cardarbot.domain.enums import (
    BodyStyle,
    CustomsFilterMode,
    Drivetrain,
    FuelType,
    OffRoadPreference,
    ScanFrequency,
    Transmission,
)
from cardarbot.domain.search_profiles import SearchFilterConfig, SearchProfileDomain
from cardarbot.domain.vehicles import NormalizedListing
from cardarbot.utils.logging import utc_now


class UserRepository:
    """Repository for users and user settings."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create_user(
        self,
        telegram_user_id: int,
        username: str | None = None,
        first_name: str | None = None,
        default_max_price_usd: int = 5000,
        default_min_profit_usd: int = 500,
        default_city: str = "Tbilisi",
        default_min_score: int = 70,
        max_alerts_per_scan: int = 10,
    ) -> UserModel:
        stmt = (
            select(UserModel)
            .options(joinedload(UserModel.settings))
            .where(UserModel.telegram_user_id == telegram_user_id)
        )
        user = self.session.execute(stmt).scalar_one_or_none()
        if user is None:
            user = UserModel(
                telegram_user_id=telegram_user_id,
                username=username,
                first_name=first_name,
                is_authorized=True,
            )
            self.session.add(user)
            self.session.flush()
            settings = UserSettingsModel(
                user_id=user.id,
                default_max_price_usd=default_max_price_usd,
                default_min_profit_usd=default_min_profit_usd,
                default_city=default_city,
                default_min_score=default_min_score,
                max_alerts_per_scan=max_alerts_per_scan,
            )
            self.session.add(settings)
            self.session.flush()
            user.settings = settings
        else:
            if username is not None and user.username != username:
                user.username = username
            if first_name is not None and user.first_name != first_name:
                user.first_name = first_name
            if user.settings is None:
                settings = UserSettingsModel(
                    user_id=user.id,
                    default_max_price_usd=default_max_price_usd,
                    default_min_profit_usd=default_min_profit_usd,
                    default_city=default_city,
                    default_min_score=default_min_score,
                    max_alerts_per_scan=max_alerts_per_scan,
                )
                self.session.add(settings)
                self.session.flush()
                user.settings = settings
        return user

    def get_by_telegram_id(self, telegram_user_id: int) -> UserModel | None:
        stmt = (
            select(UserModel)
            .options(joinedload(UserModel.settings))
            .where(UserModel.telegram_user_id == telegram_user_id)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def update_settings(self, user_id: int, **kwargs: Any) -> UserSettingsModel:
        stmt = select(UserSettingsModel).where(UserSettingsModel.user_id == user_id)
        settings = self.session.execute(stmt).scalar_one_or_none()
        if settings is None:
            settings = UserSettingsModel(user_id=user_id)
            self.session.add(settings)
            self.session.flush()
        for key, value in kwargs.items():
            if hasattr(settings, key):
                setattr(settings, key, value)
        settings.updated_at = utc_now()
        self.session.flush()
        return settings


class SearchProfileRepository:
    """Repository for search profiles with strict user ownership enforcement."""

    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _to_domain(model: SearchProfileModel) -> SearchProfileDomain:
        fc = model.filter_config
        if fc is None:
            filters = SearchFilterConfig(scan_frequency=ScanFrequency(model.scan_frequency))
        else:
            filters = SearchFilterConfig(
                makes=list(fc.makes_json or []),
                models=list(fc.models_json or []),
                fuels=[FuelType(f) for f in (fc.fuels_json or [])],
                body_styles=[BodyStyle(b) for b in (fc.body_styles_json or [])],
                drivetrains=[Drivetrain(d) for d in (fc.drivetrains_json or [])],
                off_road_preference=OffRoadPreference(fc.off_road_preference or "any"),
                transmissions=[Transmission(t) for t in (fc.transmissions_json or [])],
                min_price_usd=fc.min_price_usd,
                max_price_usd=fc.max_price_usd,
                min_year=fc.min_year,
                max_year=fc.max_year,
                min_mileage_km=fc.min_mileage_km,
                max_mileage_km=fc.max_mileage_km,
                location=fc.location,
                customs_mode=CustomsFilterMode(fc.customs_mode),
                min_profit_usd=fc.min_profit_usd,
                min_deal_score=fc.min_deal_score,
                scan_frequency=ScanFrequency(model.scan_frequency),
            )
        return SearchProfileDomain(
            id=model.id,
            user_id=model.user_id,
            name=model.name,
            is_active=model.is_active,
            filters=filters,
            last_scanned_at=model.last_scanned_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def create_profile(
        self,
        user_id: int,
        name: str,
        filters: SearchFilterConfig,
        is_active: bool = True,
    ) -> SearchProfileDomain:
        profile = SearchProfileModel(
            user_id=user_id,
            name=name,
            is_active=is_active,
            scan_frequency=filters.scan_frequency.value,
        )
        self.session.add(profile)
        self.session.flush()

        filter_row = SearchFilterModel(
            profile_id=profile.id,
            makes_json=filters.makes,
            models_json=filters.models,
            fuels_json=[f.value for f in filters.fuels],
            body_styles_json=[b.value for b in filters.body_styles],
            drivetrains_json=[d.value for d in filters.drivetrains],
            off_road_preference=filters.off_road_preference.value,
            transmissions_json=[t.value for t in filters.transmissions],
            min_price_usd=filters.min_price_usd,
            max_price_usd=filters.max_price_usd,
            min_year=filters.min_year,
            max_year=filters.max_year,
            min_mileage_km=filters.min_mileage_km,
            max_mileage_km=filters.max_mileage_km,
            location=filters.location,
            customs_mode=filters.customs_mode.value,
            min_profit_usd=filters.min_profit_usd,
            min_deal_score=filters.min_deal_score,
        )
        self.session.add(filter_row)
        self.session.flush()
        profile.filter_config = filter_row
        return self._to_domain(profile)

    def list_user_profiles(self, user_id: int) -> list[SearchProfileDomain]:
        stmt = (
            select(SearchProfileModel)
            .options(joinedload(SearchProfileModel.filter_config))
            .where(SearchProfileModel.user_id == user_id)
            .order_by(SearchProfileModel.created_at.desc())
        )
        rows = self.session.execute(stmt).scalars().all()
        return [self._to_domain(r) for r in rows]

    def list_all_active_profiles(self) -> list[SearchProfileDomain]:
        stmt = (
            select(SearchProfileModel)
            .options(joinedload(SearchProfileModel.filter_config))
            .where(SearchProfileModel.is_active.is_(True))
            .order_by(SearchProfileModel.id.asc())
        )
        rows = self.session.execute(stmt).scalars().all()
        return [self._to_domain(r) for r in rows]

    def get_profile(
        self, profile_id: int, user_id: int | None = None
    ) -> SearchProfileDomain | None:
        stmt = (
            select(SearchProfileModel)
            .options(joinedload(SearchProfileModel.filter_config))
            .where(SearchProfileModel.id == profile_id)
        )
        if user_id is not None:
            stmt = stmt.where(SearchProfileModel.user_id == user_id)
        row = self.session.execute(stmt).scalar_one_or_none()
        return self._to_domain(row) if row else None

    def update_profile(
        self,
        profile_id: int,
        user_id: int,
        name: str | None = None,
        filters: SearchFilterConfig | None = None,
        is_active: bool | None = None,
    ) -> SearchProfileDomain | None:
        stmt = (
            select(SearchProfileModel)
            .options(joinedload(SearchProfileModel.filter_config))
            .where(
                SearchProfileModel.id == profile_id,
                SearchProfileModel.user_id == user_id,
            )
        )
        profile = self.session.execute(stmt).scalar_one_or_none()
        if profile is None:
            return None

        if name is not None:
            profile.name = name
        if is_active is not None:
            profile.is_active = is_active
        if filters is not None:
            profile.scan_frequency = filters.scan_frequency.value
            fc = profile.filter_config
            if fc is None:
                fc = SearchFilterModel(profile_id=profile.id)
                self.session.add(fc)
                profile.filter_config = fc
            fc.makes_json = filters.makes
            fc.models_json = filters.models
            fc.fuels_json = [f.value for f in filters.fuels]
            fc.body_styles_json = [b.value for b in filters.body_styles]
            fc.drivetrains_json = [d.value for d in filters.drivetrains]
            fc.off_road_preference = filters.off_road_preference.value
            fc.transmissions_json = [t.value for t in filters.transmissions]
            fc.min_price_usd = filters.min_price_usd
            fc.max_price_usd = filters.max_price_usd
            fc.min_year = filters.min_year
            fc.max_year = filters.max_year
            fc.min_mileage_km = filters.min_mileage_km
            fc.max_mileage_km = filters.max_mileage_km
            fc.location = filters.location
            fc.customs_mode = filters.customs_mode.value
            fc.min_profit_usd = filters.min_profit_usd
            fc.min_deal_score = filters.min_deal_score

        profile.updated_at = utc_now()
        self.session.flush()
        return self._to_domain(profile)

    def duplicate_profile(self, profile_id: int, user_id: int) -> SearchProfileDomain | None:
        existing = self.get_profile(profile_id, user_id=user_id)
        if existing is None:
            return None
        new_name = f"{existing.name} (Copy)"
        return self.create_profile(
            user_id=user_id,
            name=new_name,
            filters=existing.filters,
            is_active=existing.is_active,
        )

    def delete_profile(self, profile_id: int, user_id: int) -> bool:
        stmt = select(SearchProfileModel).where(
            SearchProfileModel.id == profile_id,
            SearchProfileModel.user_id == user_id,
        )
        profile = self.session.execute(stmt).scalar_one_or_none()
        if profile is None:
            return False
        self.session.delete(profile)
        self.session.flush()
        return True

    def mark_scanned(self, profile_id: int) -> None:
        stmt = select(SearchProfileModel).where(SearchProfileModel.id == profile_id)
        profile = self.session.execute(stmt).scalar_one_or_none()
        if profile is not None:
            profile.last_scanned_at = utc_now()
            self.session.flush()


class ListingRepository:
    """Repository for vehicle listings, observations, and price history."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_listing(
        self,
        normalized: NormalizedListing,
        is_spam_or_rejected: bool = False,
        rejection_reasons: list[str] | None = None,
        raw_snapshot: dict[str, Any] | None = None,
    ) -> tuple[ListingModel, bool, float | None]:
        """Insert or update a listing by (source, source_listing_id).

        Returns:
            (listing_model, is_new, price_drop_usd)
        """
        stmt = select(ListingModel).where(
            ListingModel.source == normalized.source,
            ListingModel.source_listing_id == normalized.source_listing_id,
        )
        existing = self.session.execute(stmt).scalar_one_or_none()
        now = utc_now()
        price_drop_usd: float | None = None

        if existing is None:
            listing = ListingModel(
                source=normalized.source,
                source_listing_id=normalized.source_listing_id,
                url=normalized.url,
                make=normalized.make,
                model=normalized.model,
                generation=normalized.generation,
                trim=normalized.trim,
                year=normalized.year,
                fuel=normalized.fuel.value,
                powertrain=normalized.powertrain,
                body_style=normalized.body_style.value,
                drivetrain=normalized.drivetrain.value,
                transmission=normalized.transmission.value,
                engine=normalized.engine,
                mileage_km=normalized.mileage_km,
                location=normalized.location,
                customs_status=normalized.customs_status.value,
                price=normalized.price,
                currency=normalized.currency,
                usd_price=normalized.usd_price,
                description=normalized.description,
                seller_type=normalized.seller_type,
                condition_indicators=normalized.condition_indicators,
                photo_urls=normalized.photo_urls,
                is_spam_or_rejected=is_spam_or_rejected,
                rejection_reasons=rejection_reasons or [],
                publication_date=normalized.publication_date,
                first_seen=now,
                last_seen=now,
            )
            self.session.add(listing)
            self.session.flush()

            if normalized.usd_price is not None:
                ph = PriceHistoryModel(
                    listing_id=listing.id,
                    old_usd_price=None,
                    new_usd_price=normalized.usd_price,
                    price_change_usd=0.0,
                    recorded_at=now,
                )
                self.session.add(ph)

            obs = ListingObservationModel(
                listing_id=listing.id,
                observed_at=now,
                price=normalized.price,
                currency=normalized.currency,
                usd_price=normalized.usd_price,
                mileage_km=normalized.mileage_km,
                raw_snapshot=raw_snapshot or {},
            )
            self.session.add(obs)
            self.session.flush()
            return listing, True, None

        # Existing listing: check for price changes
        old_usd = existing.usd_price
        new_usd = normalized.usd_price
        if old_usd is not None and new_usd is not None and abs(new_usd - old_usd) >= 1.0:
            diff = round(new_usd - old_usd, 2)
            if diff < 0:
                price_drop_usd = abs(diff)
            ph = PriceHistoryModel(
                listing_id=existing.id,
                old_usd_price=old_usd,
                new_usd_price=new_usd,
                price_change_usd=diff,
                recorded_at=now,
            )
            self.session.add(ph)

        existing.url = normalized.url
        existing.make = normalized.make or existing.make
        existing.model = normalized.model or existing.model
        existing.generation = normalized.generation or existing.generation
        existing.trim = normalized.trim or existing.trim
        existing.year = normalized.year or existing.year
        if normalized.fuel != FuelType.UNKNOWN:
            existing.fuel = normalized.fuel.value
            existing.powertrain = normalized.powertrain
        if normalized.body_style != BodyStyle.UNKNOWN:
            existing.body_style = normalized.body_style.value
        if normalized.drivetrain != Drivetrain.UNKNOWN:
            existing.drivetrain = normalized.drivetrain.value
        if normalized.transmission != Transmission.UNKNOWN:
            existing.transmission = normalized.transmission.value
        existing.engine = normalized.engine or existing.engine
        if normalized.mileage_km is not None:
            existing.mileage_km = normalized.mileage_km
        existing.location = normalized.location or existing.location
        if normalized.customs_status.value != "unknown":
            existing.customs_status = normalized.customs_status.value
        existing.price = normalized.price
        existing.currency = normalized.currency
        existing.usd_price = normalized.usd_price
        existing.description = normalized.description or existing.description
        existing.seller_type = normalized.seller_type or existing.seller_type
        if normalized.condition_indicators:
            existing.condition_indicators = normalized.condition_indicators
        if normalized.photo_urls:
            existing.photo_urls = normalized.photo_urls
        existing.is_spam_or_rejected = is_spam_or_rejected
        existing.rejection_reasons = rejection_reasons or []
        existing.last_seen = now

        obs = ListingObservationModel(
            listing_id=existing.id,
            observed_at=now,
            price=normalized.price,
            currency=normalized.currency,
            usd_price=normalized.usd_price,
            mileage_km=normalized.mileage_km,
            raw_snapshot=raw_snapshot or {},
        )
        self.session.add(obs)
        self.session.flush()
        return existing, False, price_drop_usd

    def get_by_id(self, listing_id: int) -> ListingModel | None:
        stmt = (
            select(ListingModel)
            .options(
                joinedload(ListingModel.price_history),
                joinedload(ListingModel.evaluations),
            )
            .where(ListingModel.id == listing_id)
        )
        return self.session.execute(stmt).unique().scalar_one_or_none()

    def list_clean_listings(
        self, make: str | None = None, model: str | None = None
    ) -> list[ListingModel]:
        stmt = select(ListingModel).where(
            ListingModel.is_spam_or_rejected.is_(False),
            ListingModel.usd_price.is_not(None),
        )
        if make:
            stmt = stmt.where(ListingModel.make.ilike(make))
        if model:
            stmt = stmt.where(ListingModel.model.ilike(model))
        return list(self.session.execute(stmt).scalars().all())

    def get_price_history(self, listing_id: int) -> list[PriceHistoryModel]:
        stmt = (
            select(PriceHistoryModel)
            .where(PriceHistoryModel.listing_id == listing_id)
            .order_by(PriceHistoryModel.recorded_at.asc())
        )
        return list(self.session.execute(stmt).scalars().all())


class DealRepository:
    """Repository for deal evaluations, saved cars, dismissed cars, notifications, and source health."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def save_evaluation(
        self,
        listing_id: int,
        evaluation: DealEvaluationDomain,
    ) -> DealEvaluationModel:
        comp_snapshot = ComparableSnapshotModel(
            listing_id=listing_id,
            comparable_count=evaluation.valuation.comparable_count,
            median_asking_usd=evaluation.valuation.median_asking_usd,
            q25_asking_usd=evaluation.valuation.q25_asking_usd,
            q75_asking_usd=evaluation.valuation.q75_asking_usd,
            conservative_resale_usd=evaluation.valuation.conservative_resale_usd,
            resale_discount_percent=evaluation.valuation.resale_discount_percent,
            confidence=evaluation.valuation.confidence.value,
            comparables_json=[c.model_dump() for c in evaluation.valuation.comparables],
        )
        self.session.add(comp_snapshot)
        self.session.flush()

        eval_model = DealEvaluationModel(
            listing_id=listing_id,
            profile_id=evaluation.matched_profile_id,
            comparable_snapshot_id=comp_snapshot.id,
            asking_price_usd=evaluation.profit.asking_price_usd,
            conservative_resale_usd=evaluation.profit.conservative_resale_usd,
            gross_spread_usd=evaluation.profit.gross_spread_usd,
            expenses_usd=evaluation.profit.total_expenses_usd,
            expenses_breakdown_json=evaluation.profit.expenses.model_dump(),
            net_profit_usd=evaluation.profit.net_profit_usd,
            return_percentage=evaluation.profit.return_percentage,
            score=evaluation.score.total_score,
            classification=evaluation.score.classification.value,
            confidence=evaluation.profit.confidence.value,
            hard_rejected=evaluation.score.hard_rejected,
            reasons_json=evaluation.score.reasons,
            risks_json=evaluation.score.risks,
            rejection_reasons_json=evaluation.score.rejection_reasons,
        )
        self.session.add(eval_model)
        self.session.flush()
        return eval_model

    def get_latest_evaluation(
        self, listing_id: int
    ) -> tuple[DealEvaluationModel | None, ComparableSnapshotModel | None]:
        stmt = (
            select(DealEvaluationModel)
            .where(DealEvaluationModel.listing_id == listing_id)
            .order_by(DealEvaluationModel.evaluated_at.desc(), DealEvaluationModel.id.desc())
            .limit(1)
        )
        eval_model = self.session.execute(stmt).scalar_one_or_none()
        if eval_model is None:
            return None, None
        comp_model = None
        if eval_model.comparable_snapshot_id is not None:
            comp_stmt = select(ComparableSnapshotModel).where(
                ComparableSnapshotModel.id == eval_model.comparable_snapshot_id
            )
            comp_model = self.session.execute(comp_stmt).scalar_one_or_none()
        return eval_model, comp_model

    def save_deal_for_user(
        self, user_id: int, listing_id: int, notes: str | None = None
    ) -> SavedDealModel:
        # Remove from dismissed if present
        dismissed_stmt = select(DismissedDealModel).where(
            DismissedDealModel.user_id == user_id,
            DismissedDealModel.listing_id == listing_id,
        )
        dismissed = self.session.execute(dismissed_stmt).scalar_one_or_none()
        if dismissed is not None:
            self.session.delete(dismissed)

        stmt = select(SavedDealModel).where(
            SavedDealModel.user_id == user_id,
            SavedDealModel.listing_id == listing_id,
        )
        existing = self.session.execute(stmt).scalar_one_or_none()
        if existing is not None:
            if notes is not None:
                existing.notes = notes
            self.session.flush()
            return existing

        saved = SavedDealModel(user_id=user_id, listing_id=listing_id, notes=notes)
        self.session.add(saved)
        self.session.flush()
        return saved

    def remove_saved_deal(self, user_id: int, listing_id: int) -> bool:
        stmt = select(SavedDealModel).where(
            SavedDealModel.user_id == user_id,
            SavedDealModel.listing_id == listing_id,
        )
        existing = self.session.execute(stmt).scalar_one_or_none()
        if existing is None:
            return False
        self.session.delete(existing)
        self.session.flush()
        return True

    def dismiss_deal_for_user(self, user_id: int, listing_id: int) -> DismissedDealModel:
        # Remove from saved if present
        self.remove_saved_deal(user_id, listing_id)
        stmt = select(DismissedDealModel).where(
            DismissedDealModel.user_id == user_id,
            DismissedDealModel.listing_id == listing_id,
        )
        existing = self.session.execute(stmt).scalar_one_or_none()
        if existing is not None:
            return existing
        dismissed = DismissedDealModel(user_id=user_id, listing_id=listing_id)
        self.session.add(dismissed)
        self.session.flush()
        return dismissed

    def list_saved_listing_ids(self, user_id: int) -> list[int]:
        stmt = (
            select(SavedDealModel.listing_id)
            .where(SavedDealModel.user_id == user_id)
            .order_by(SavedDealModel.saved_at.desc())
        )
        return list(self.session.execute(stmt).scalars().all())

    def list_dismissed_listing_ids(self, user_id: int) -> list[int]:
        stmt = (
            select(DismissedDealModel.listing_id)
            .where(DismissedDealModel.user_id == user_id)
            .order_by(DismissedDealModel.dismissed_at.desc())
        )
        return list(self.session.execute(stmt).scalars().all())

    def was_recently_notified(
        self,
        user_id: int,
        listing_id: int,
        current_price_usd: float,
        min_price_drop_usd: float = 150.0,
    ) -> tuple[bool, str]:
        """Check whether user was already notified for this listing unless price dropped meaningfully."""
        stmt = (
            select(NotificationModel)
            .where(
                NotificationModel.user_id == user_id,
                NotificationModel.listing_id == listing_id,
                NotificationModel.delivery_status == "sent",
            )
            .order_by(NotificationModel.sent_at.desc(), NotificationModel.id.desc())
            .limit(1)
        )
        last_notif = self.session.execute(stmt).scalar_one_or_none()
        if last_notif is None:
            return False, "new_deal"

        price_drop = last_notif.notified_price_usd - current_price_usd
        if price_drop >= min_price_drop_usd:
            return False, "price_drop"
        return True, "duplicate"

    def record_notification(
        self,
        user_id: int,
        listing_id: int,
        notified_price_usd: float,
        score: int,
        profile_id: int | None = None,
        alert_type: str = "new_deal",
        delivery_status: str = "sent",
        retry_count: int = 0,
    ) -> NotificationModel:
        notif = NotificationModel(
            user_id=user_id,
            listing_id=listing_id,
            profile_id=profile_id,
            notified_price_usd=notified_price_usd,
            score=score,
            alert_type=alert_type,
            delivery_status=delivery_status,
            retry_count=retry_count,
        )
        self.session.add(notif)
        self.session.flush()
        return notif

    def update_source_health(
        self,
        source_name: str,
        status_mode: str,
        error_message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> SourceHealthModel:
        stmt = select(SourceHealthModel).where(SourceHealthModel.source_name == source_name)
        health = self.session.execute(stmt).scalar_one_or_none()
        now = utc_now()
        if health is None:
            health = SourceHealthModel(
                source_name=source_name,
                status_mode=status_mode,
                last_check_at=now,
                last_success_at=now if error_message is None and status_mode == "live" else None,
                consecutive_failures=1 if error_message else 0,
                last_error=error_message,
                details_json=details or {},
            )
            self.session.add(health)
        else:
            health.status_mode = status_mode
            health.last_check_at = now
            if error_message is None and status_mode == "live":
                health.last_success_at = now
                health.consecutive_failures = 0
                health.last_error = None
            elif error_message:
                health.consecutive_failures += 1
                health.last_error = error_message
            if details is not None:
                health.details_json = details
        self.session.flush()
        return health

    def get_source_health(self, source_name: str = "myauto") -> SourceHealthModel | None:
        stmt = select(SourceHealthModel).where(SourceHealthModel.source_name == source_name)
        return self.session.execute(stmt).scalar_one_or_none()

    def create_scan_job(
        self, profile_id: int | None = None, trigger_type: str = "scheduled"
    ) -> ScanJobModel:
        job = ScanJobModel(
            profile_id=profile_id,
            trigger_type=trigger_type,
            status="running",
            started_at=utc_now(),
        )
        self.session.add(job)
        self.session.flush()
        return job

    def finish_scan_job(
        self,
        job_id: int,
        status: str = "completed",
        listings_fetched: int = 0,
        deals_found: int = 0,
        alerts_sent: int = 0,
        error_message: str | None = None,
    ) -> ScanJobModel | None:
        stmt = select(ScanJobModel).where(ScanJobModel.id == job_id)
        job = self.session.execute(stmt).scalar_one_or_none()
        if job is not None:
            job.status = status
            job.listings_fetched = listings_fetched
            job.deals_found = deals_found
            job.alerts_sent = alerts_sent
            job.error_message = error_message
            job.completed_at = utc_now()
            self.session.flush()
        return job
