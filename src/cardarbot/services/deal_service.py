from __future__ import annotations

from cardarbot.analysis.comparables import select_comparables_and_estimate_value
from cardarbot.analysis.profit import calculate_profit_estimate
from cardarbot.analysis.scoring import calculate_deal_score
from cardarbot.analysis.spam_filter import evaluate_listing_credibility
from cardarbot.config import Settings
from cardarbot.database.models import ListingModel
from cardarbot.database.repositories import DealRepository, ListingRepository
from cardarbot.database.session import DatabaseManager
from cardarbot.domain.deals import DealEvaluationDomain
from cardarbot.domain.enums import (
    BodyStyle,
    CustomsFilterMode,
    CustomsStatus,
    Drivetrain,
    FuelType,
    OffRoadPreference,
    Transmission,
)
from cardarbot.domain.search_profiles import SearchFilterConfig, SearchProfileDomain
from cardarbot.domain.vehicles import NormalizedListing, is_verified_off_road_vehicle


def listing_model_to_domain(row: ListingModel) -> NormalizedListing:
    return NormalizedListing(
        source=row.source,
        source_listing_id=row.source_listing_id,
        url=row.url,
        make=row.make,
        model=row.model,
        generation=row.generation,
        trim=row.trim,
        year=row.year,
        fuel=FuelType(row.fuel) if row.fuel in FuelType._value2member_map_ else FuelType.UNKNOWN,
        powertrain=row.powertrain,
        body_style=BodyStyle(row.body_style)
        if row.body_style in BodyStyle._value2member_map_
        else BodyStyle.UNKNOWN,
        drivetrain=Drivetrain(row.drivetrain)
        if row.drivetrain in Drivetrain._value2member_map_
        else Drivetrain.UNKNOWN,
        transmission=Transmission(row.transmission)
        if row.transmission in Transmission._value2member_map_
        else Transmission.UNKNOWN,
        engine=row.engine,
        mileage_km=row.mileage_km,
        location=row.location,
        customs_status=CustomsStatus(row.customs_status)
        if row.customs_status in CustomsStatus._value2member_map_
        else CustomsStatus.UNKNOWN,
        price=row.price,
        currency=row.currency,
        usd_price=row.usd_price,
        description=row.description,
        seller_type=row.seller_type,
        condition_indicators=dict(row.condition_indicators or {}),
        photo_urls=list(row.photo_urls or []),
        publication_date=row.publication_date,
        first_seen=row.first_seen,
        last_seen=row.last_seen,
    )


def does_listing_match_filter(listing: NormalizedListing, filters: SearchFilterConfig) -> bool:
    """Check whether a normalized vehicle listing satisfies all SearchFilterConfig criteria."""
    if listing.usd_price is None:
        return False
    if listing.usd_price < filters.min_price_usd or listing.usd_price > filters.max_price_usd:
        return False

    if filters.makes and (
        not listing.make or listing.make.lower() not in {m.lower() for m in filters.makes}
    ):
        return False

    if filters.models and (
        not listing.model or listing.model.lower() not in {m.lower() for m in filters.models}
    ):
        return False

    if filters.fuels and listing.fuel not in filters.fuels:
        return False

    if filters.body_styles and listing.body_style not in filters.body_styles:
        return False

    if filters.drivetrains and listing.drivetrain not in filters.drivetrains:
        return False

    if filters.off_road_preference == OffRoadPreference.AWD_4WD_REQUIRED:
        if listing.drivetrain not in {Drivetrain.AWD, Drivetrain.FOUR_WD}:
            return False
    elif (
        filters.off_road_preference == OffRoadPreference.VERIFIED_OFF_ROAD_MODEL
        and not is_verified_off_road_vehicle(listing.make, listing.model)
    ):
        return False

    if filters.transmissions and listing.transmission not in filters.transmissions:
        return False

    if filters.min_year is not None and (listing.year is None or listing.year < filters.min_year):
        return False
    if filters.max_year is not None and (listing.year is None or listing.year > filters.max_year):
        return False

    if filters.min_mileage_km is not None and (
        listing.mileage_km is None or listing.mileage_km < filters.min_mileage_km
    ):
        return False
    if filters.max_mileage_km is not None and (
        listing.mileage_km is not None and listing.mileage_km > filters.max_mileage_km
    ):
        return False

    if (
        filters.location
        and listing.location
        and filters.location.lower() != listing.location.lower()
    ):
        return False

    # Unknown customs status must not be treated as confirmed cleared
    return not (
        filters.customs_mode == CustomsFilterMode.CLEARED_ONLY
        and listing.customs_status != CustomsStatus.CLEARED
    )


class DealService:
    """Orchestrates listing ingestion, spam filtering, comparable valuation, profit & deal scoring."""

    def __init__(self, db: DatabaseManager, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    def ingest_and_evaluate_listings(
        self,
        listings: list[NormalizedListing],
        profile: SearchProfileDomain | None = None,
    ) -> list[tuple[ListingModel, DealEvaluationDomain]]:
        """Persist listings, run spam detection, compute comparables, and persist evaluations."""
        results: list[tuple[ListingModel, DealEvaluationDomain]] = []
        if not listings:
            return results

        with self.db.session() as session:
            l_repo = ListingRepository(session)
            d_repo = DealRepository(session)

            # First pass: run spam filter and upsert all incoming listings so clean comparables are in DB
            upserted_rows: list[tuple[ListingModel, NormalizedListing]] = []
            for norm in listings:
                spam_res = evaluate_listing_credibility(norm)
                norm.condition_indicators.update(spam_res.condition_indicators)
                norm.condition_indicators["is_rejected"] = spam_res.is_rejected
                row, _, _ = l_repo.upsert_listing(
                    norm,
                    is_spam_or_rejected=spam_res.is_rejected,
                    rejection_reasons=spam_res.rejection_reasons,
                )
                upserted_rows.append((row, norm))

            # Load clean pool from database for comparable valuation
            clean_db_rows = l_repo.list_clean_listings()
            clean_pool = [listing_model_to_domain(r) for r in clean_db_rows]

            min_profit = (
                float(profile.filters.min_profit_usd)
                if profile is not None
                else float(self.settings.default_min_profit_usd)
            )

            for row, norm in upserted_rows:
                spam_res = evaluate_listing_credibility(norm)
                valuation = select_comparables_and_estimate_value(
                    candidate=norm,
                    pool=clean_pool,
                    min_comparables=self.settings.min_comparables,
                    resale_discount_percent=self.settings.resale_discount_percent,
                )
                profit = calculate_profit_estimate(
                    listing=norm,
                    valuation=valuation,
                    min_profit_usd=min_profit,
                    default_expense_buffer_usd=float(self.settings.default_expense_buffer_usd),
                )
                score = calculate_deal_score(
                    listing=norm,
                    spam_result=spam_res,
                    valuation=valuation,
                    profit=profit,
                    min_comparables=self.settings.min_comparables,
                    target_profit_usd=min_profit,
                )
                eval_domain = DealEvaluationDomain(
                    listing_id=row.id,
                    source_listing_id=norm.source_listing_id,
                    matched_profile_id=profile.id if profile else None,
                    matched_profile_name=profile.name if profile else None,
                    valuation=valuation,
                    profit=profit,
                    score=score,
                )
                d_repo.save_evaluation(row.id, eval_domain)
                results.append((row, eval_domain))

        return results
