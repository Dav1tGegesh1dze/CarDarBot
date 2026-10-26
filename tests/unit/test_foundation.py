from __future__ import annotations

import pytest
from pydantic import ValidationError

from cardarbot.config import Settings
from cardarbot.database.models import Base
from cardarbot.database.repositories import (
    DealRepository,
    ListingRepository,
    SearchProfileRepository,
    UserRepository,
)
from cardarbot.database.session import DatabaseManager
from cardarbot.domain.enums import (
    BodyStyle,
    CustomsFilterMode,
    CustomsStatus,
    Drivetrain,
    FuelType,
    OffRoadPreference,
    PowertrainGroup,
)
from cardarbot.domain.search_profiles import SearchFilterConfig
from cardarbot.domain.vehicles import (
    NormalizedListing,
    expand_powertrain_group,
    is_verified_off_road_vehicle,
    resolve_manufacturer,
    resolve_model,
    validate_make_model_combination,
)
from cardarbot.utils.currency import convert_to_usd, normalize_currency_code
from cardarbot.utils.logging import SecretRedactingFilter, format_tbilisi_time, utc_now


def test_settings_validation_and_secret_protection() -> None:
    settings = Settings(
        TELEGRAM_BOT_TOKEN="123456789:ABCDEF1234567890abcdef1234567890",
        TELEGRAM_ALLOWED_USER_IDS="111222333, 444555666",
        DEFAULT_MAX_PRICE_USD=5000,
    )
    assert settings.telegram_allowed_user_ids == [111222333, 444555666]
    assert settings.has_valid_bot_token() is True
    assert "ABCDEF" not in repr(settings.telegram_bot_token)


def test_secret_redacting_log_filter() -> None:
    import logging

    filter_obj = SecretRedactingFilter(explicit_secrets=["super_secret_val"])
    record = logging.LogRecord(
        name="cardarbot",
        level=logging.INFO,
        pathname="",
        lineno=1,
        msg="Token 123456789:AAH_test_token_12345678901234567890 and super_secret_val",
        args=(),
        exc_info=None,
    )
    filter_obj.filter(record)
    assert "AAH_test_token" not in record.msg
    assert "super_secret_val" not in record.msg
    assert "[REDACTED_TELEGRAM_TOKEN]" in record.msg


def test_currency_normalization_and_conversion() -> None:
    assert normalize_currency_code("$") == "USD"
    assert normalize_currency_code("₾") == "GEL"
    assert normalize_currency_code("ლარი") == "GEL"
    assert normalize_currency_code("€") == "EUR"
    assert convert_to_usd(3000, "USD") == 3000.0
    assert convert_to_usd(10000, "GEL", gel_to_usd=0.37) == 3700.0
    assert convert_to_usd(2000, "EUR", eur_to_usd=1.08) == 2160.0


def test_catalog_and_powertrain_invariants() -> None:
    assert resolve_manufacturer("ტოიოტა") == "Toyota"
    assert resolve_model("Toyota", "პრიუსი") == "Prius"
    assert resolve_model("Toyota", "Aqua") == "Aqua"
    assert validate_make_model_combination("Toyota", "Prius") is True
    assert validate_make_model_combination("Toyota", "X5") is False
    assert validate_make_model_combination("BMW", "X5") is True

    # Powertrain invariant: Never classify a hybrid as fully electric
    ev_fuels = expand_powertrain_group(PowertrainGroup.EV)
    assert ev_fuels == [FuelType.ELECTRIC]
    assert FuelType.HYBRID not in ev_fuels
    assert FuelType.PLUGIN_HYBRID not in ev_fuels

    # Off-road invariant: Do not infer genuine off-road capability from body style alone
    assert is_verified_off_road_vehicle("Toyota", "4Runner") is True
    assert is_verified_off_road_vehicle("Toyota", "RAV4") is False
    assert is_verified_off_road_vehicle("Jeep", "Wrangler") is True


def test_search_filter_validation() -> None:
    with pytest.raises(ValidationError):
        SearchFilterConfig(min_price_usd=6000, max_price_usd=4000)
    with pytest.raises(ValidationError):
        SearchFilterConfig(min_year=2020, max_year=2015)

    cfg = SearchFilterConfig(
        makes=["Toyota"],
        models=["Prius"],
        fuels=[FuelType.HYBRID],
        body_styles=[BodyStyle.HATCHBACK],
        drivetrains=[Drivetrain.FWD],
        off_road_preference=OffRoadPreference.ANY,
        min_price_usd=500,
        max_price_usd=5000,
        customs_mode=CustomsFilterMode.CLEARED_ONLY,
    )
    summary = cfg.format_summary("Toyota Hybrid Deals")
    assert "Toyota Hybrid Deals" in summary
    assert "Make: Toyota" in summary
    assert "Model: Prius" in summary
    assert "Customs: Cleared" in summary


def test_database_tables_and_repositories() -> None:
    db = DatabaseManager("sqlite:///:memory:")
    db.init_db()

    expected_tables = {
        "users",
        "user_settings",
        "search_profiles",
        "search_filters",
        "listings",
        "listing_observations",
        "price_history",
        "comparable_snapshots",
        "deal_evaluations",
        "saved_deals",
        "dismissed_deals",
        "notifications",
        "scan_jobs",
        "source_health",
    }
    assert expected_tables.issubset(set(Base.metadata.tables.keys()))

    with db.session() as session:
        user_repo = UserRepository(session)
        profile_repo = SearchProfileRepository(session)
        listing_repo = ListingRepository(session)
        deal_repo = DealRepository(session)

        user1 = user_repo.get_or_create_user(telegram_user_id=1001, username="alice")
        user2 = user_repo.get_or_create_user(telegram_user_id=1002, username="bob")

        filters = SearchFilterConfig(makes=["Toyota"], models=["Prius"], max_price_usd=4500)
        p1 = profile_repo.create_profile(user1.id, "Toyota Hybrid Deals", filters)
        assert p1.id is not None

        # User2 cannot modify or delete User1's profile
        assert profile_repo.update_profile(p1.id, user2.id, name="Hacked") is None
        assert profile_repo.delete_profile(p1.id, user2.id) is False

        # User1 can duplicate and update
        dup = profile_repo.duplicate_profile(p1.id, user1.id)
        assert dup is not None
        assert dup.name == "Toyota Hybrid Deals (Copy)"

        # Listing deduplication and price history tracking
        norm = NormalizedListing(
            source="myauto",
            source_listing_id="998877",
            url="https://www.myauto.ge/ka/pr/998877",
            make="Toyota",
            model="Prius",
            year=2013,
            fuel=FuelType.HYBRID,
            powertrain="hybrid",
            customs_status=CustomsStatus.CLEARED,
            price=3500.0,
            currency="USD",
            usd_price=3500.0,
            location="Tbilisi",
        )
        row1, is_new1, drop1 = listing_repo.upsert_listing(norm)
        assert is_new1 is True
        assert drop1 is None

        # Price drop update
        norm.price = 3200.0
        norm.usd_price = 3200.0
        row2, is_new2, drop2 = listing_repo.upsert_listing(norm)
        assert is_new2 is False
        assert row2.id == row1.id
        assert drop2 == 300.0

        history = listing_repo.get_price_history(row1.id)
        assert len(history) == 2

        # Notification deduplication & price-drop re-alerting
        was_notif, reason = deal_repo.was_recently_notified(user1.id, row1.id, 3500.0)
        assert was_notif is False
        assert reason == "new_deal"

        deal_repo.record_notification(user1.id, row1.id, 3500.0, score=82, profile_id=p1.id)
        was_notif_again, reason_again = deal_repo.was_recently_notified(user1.id, row1.id, 3500.0)
        assert was_notif_again is True
        assert reason_again == "duplicate"

        was_notif_drop, reason_drop = deal_repo.was_recently_notified(user1.id, row1.id, 3200.0)
        assert was_notif_drop is False
        assert reason_drop == "price_drop"


def test_tbilisi_time_formatting() -> None:
    now = utc_now()
    formatted = format_tbilisi_time(now)
    assert "GET" in formatted
