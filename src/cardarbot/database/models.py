from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from cardarbot.utils.logging import utc_now


class Base(DeclarativeBase):
    pass


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True
    )
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_authorized: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    settings: Mapped[UserSettingsModel | None] = relationship(
        "UserSettingsModel", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    search_profiles: Mapped[list[SearchProfileModel]] = relationship(
        "SearchProfileModel", back_populates="user", cascade="all, delete-orphan"
    )


class UserSettingsModel(Base):
    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    default_max_price_usd: Mapped[int] = mapped_column(Integer, default=5000, nullable=False)
    default_min_profit_usd: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    default_city: Mapped[str] = mapped_column(String(64), default="Tbilisi", nullable=False)
    default_min_score: Mapped[int] = mapped_column(Integer, default=70, nullable=False)
    preferred_currency: Mapped[str] = mapped_column(String(8), default="USD", nullable=False)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    quiet_hours_start: Mapped[int | None] = mapped_column(Integer, nullable=True)  # e.g., 23
    quiet_hours_end: Mapped[int | None] = mapped_column(Integer, nullable=True)  # e.g., 8
    daily_summary_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_alerts_per_scan: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    preferred_language: Mapped[str] = mapped_column(String(8), default="en", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    user: Mapped[UserModel] = relationship("UserModel", back_populates="settings")


class SearchProfileModel(Base):
    __tablename__ = "search_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    scan_frequency: Mapped[str] = mapped_column(String(32), default="daily", nullable=False)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    user: Mapped[UserModel] = relationship("UserModel", back_populates="search_profiles")
    filter_config: Mapped[SearchFilterModel | None] = relationship(
        "SearchFilterModel", back_populates="profile", uselist=False, cascade="all, delete-orphan"
    )


class SearchFilterModel(Base):
    __tablename__ = "search_filters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("search_profiles.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    makes_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    models_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    fuels_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    body_styles_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    drivetrains_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    off_road_preference: Mapped[str] = mapped_column(String(64), default="any", nullable=False)
    transmissions_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    min_price_usd: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    max_price_usd: Mapped[int] = mapped_column(Integer, default=5000, nullable=False)
    min_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_mileage_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_mileage_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location: Mapped[str] = mapped_column(String(64), default="Tbilisi", nullable=False)
    customs_mode: Mapped[str] = mapped_column(String(32), default="cleared_only", nullable=False)
    min_profit_usd: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    min_deal_score: Mapped[int] = mapped_column(Integer, default=70, nullable=False)

    profile: Mapped[SearchProfileModel] = relationship(
        "SearchProfileModel", back_populates="filter_config"
    )


class ListingModel(Base):
    __tablename__ = "listings"
    __table_args__ = (UniqueConstraint("source", "source_listing_id", name="uq_listing_source_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="myauto", index=True)
    source_listing_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(512), nullable=False)
    make: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    generation: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trim: Mapped[str | None] = mapped_column(String(64), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    fuel: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    powertrain: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    body_style: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    drivetrain: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    transmission: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    engine: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mileage_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    customs_status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(16), default="USD", nullable=False)
    usd_price: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    seller_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    condition_indicators: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    photo_urls: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    is_spam_or_rejected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rejection_reasons: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    publication_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    observations: Mapped[list[ListingObservationModel]] = relationship(
        "ListingObservationModel", back_populates="listing", cascade="all, delete-orphan"
    )
    price_history: Mapped[list[PriceHistoryModel]] = relationship(
        "PriceHistoryModel", back_populates="listing", cascade="all, delete-orphan"
    )
    evaluations: Mapped[list[DealEvaluationModel]] = relationship(
        "DealEvaluationModel", back_populates="listing", cascade="all, delete-orphan"
    )


class ListingObservationModel(Base):
    __tablename__ = "listing_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(16), default="USD", nullable=False)
    usd_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    mileage_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    listing: Mapped[ListingModel] = relationship("ListingModel", back_populates="observations")


class PriceHistoryModel(Base):
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    old_usd_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_usd_price: Mapped[float] = mapped_column(Float, nullable=False)
    price_change_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    listing: Mapped[ListingModel] = relationship("ListingModel", back_populates="price_history")


class ComparableSnapshotModel(Base):
    __tablename__ = "comparable_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    comparable_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    median_asking_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    q25_asking_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    q75_asking_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    conservative_resale_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    resale_discount_percent: Mapped[float] = mapped_column(Float, default=10.0, nullable=False)
    confidence: Mapped[str] = mapped_column(String(32), default="uncertain", nullable=False)
    comparables_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DealEvaluationModel(Base):
    __tablename__ = "deal_evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("search_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    comparable_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("comparable_snapshots.id", ondelete="SET NULL"), nullable=True
    )
    asking_price_usd: Mapped[float] = mapped_column(Float, nullable=False)
    conservative_resale_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    gross_spread_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    expenses_usd: Mapped[float] = mapped_column(Float, default=400.0, nullable=False)
    expenses_breakdown_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    net_profit_usd: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    return_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    classification: Mapped[str] = mapped_column(String(32), default="ignore", nullable=False)
    confidence: Mapped[str] = mapped_column(String(32), default="uncertain", nullable=False)
    hard_rejected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reasons_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    risks_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    rejection_reasons_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    listing: Mapped[ListingModel] = relationship("ListingModel", back_populates="evaluations")


class SavedDealModel(Base):
    __tablename__ = "saved_deals"
    __table_args__ = (UniqueConstraint("user_id", "listing_id", name="uq_user_saved_listing"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DismissedDealModel(Base):
    __tablename__ = "dismissed_deals"
    __table_args__ = (UniqueConstraint("user_id", "listing_id", name="uq_user_dismissed_listing"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dismissed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class NotificationModel(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("search_profiles.id", ondelete="SET NULL"), nullable=True
    )
    notified_price_usd: Mapped[float] = mapped_column(Float, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    alert_type: Mapped[str] = mapped_column(String(32), default="new_deal", nullable=False)
    delivery_status: Mapped[str] = mapped_column(String(32), default="sent", nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ScanJobModel(Base):
    __tablename__ = "scan_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("search_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    trigger_type: Mapped[str] = mapped_column(String(32), default="scheduled", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False)
    listings_fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deals_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    alerts_sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SourceHealthModel(Base):
    __tablename__ = "source_health"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status_mode: Mapped[str] = mapped_column(
        String(32), default="import_only", nullable=False
    )  # live, import_only, temporarily_unavailable, unsupported
    last_check_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    details_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
