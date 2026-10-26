from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from cardarbot.cli import main as cli_main
from cardarbot.config import Settings
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
    Drivetrain,
    FuelType,
    OffRoadPreference,
    ScanFrequency,
    SourceStatusMode,
)
from cardarbot.domain.search_profiles import SearchFilterConfig
from cardarbot.services.deal_service import DealService
from cardarbot.services.search_service import SearchService
from cardarbot.sources.import_adapter import ListingImportAdapter
from cardarbot.sources.myauto import MyAutoSource


@pytest.mark.asyncio
async def test_end_to_end_pipeline_persistence_and_network_fallback(tmp_path: Path) -> None:
    db_file = tmp_path / "e2e_cardarbot.db"
    db_url = f"sqlite:///{db_file}"
    settings = Settings(
        DATABASE_URL=db_url,
        TELEGRAM_BOT_TOKEN="123456789:ABCDEF1234567890abcdef1234567890",
        TELEGRAM_ALLOWED_USER_IDS=[555001],
        MIN_COMPARABLES=5,
        RESALE_DISCOUNT_PERCENT=10.0,
        DEFAULT_EXPENSE_BUFFER_USD=400,
    )

    # 1. Initialize database and create user + multiple search profiles
    db1 = DatabaseManager(db_url)
    db1.init_db()
    with db1.session() as session:
        u_repo = UserRepository(session)
        p_repo = SearchProfileRepository(session)
        user = u_repo.get_or_create_user(telegram_user_id=555001, username="e2e_user")

        p1 = p_repo.create_profile(
            user.id,
            "Toyota Hybrid Deals",
            SearchFilterConfig(
                makes=["Toyota"],
                models=["Prius"],
                fuels=[FuelType.HYBRID],
                body_styles=[BodyStyle.HATCHBACK],
                drivetrains=[Drivetrain.FWD],
                off_road_preference=OffRoadPreference.ANY,
                min_price_usd=500,
                max_price_usd=4500,
                min_year=2010,
                max_year=2017,
                location="Tbilisi",
                customs_mode=CustomsFilterMode.CLEARED_ONLY,
                min_profit_usd=500,
                min_deal_score=70,
                scan_frequency=ScanFrequency.DAILY,
            ),
        )
        p2 = p_repo.create_profile(
            user.id,
            "Verified Off-Road 4x4",
            SearchFilterConfig(
                makes=["Toyota"],
                models=["4Runner"],
                drivetrains=[Drivetrain.FOUR_WD],
                off_road_preference=OffRoadPreference.VERIFIED_OFF_ROAD_MODEL,
                min_price_usd=1000,
                max_price_usd=12000,
            ),
        )
        assert p1.id is not None and p2.id is not None

    # 2. Simulate application restart by creating a brand new DatabaseManager on the same SQLite file
    db2 = DatabaseManager(db_url)
    with db2.session() as session:
        p_repo = SearchProfileRepository(session)
        saved_profiles = p_repo.list_all_active_profiles()
        assert len(saved_profiles) == 2

    # 3. Export a batch of realistic listings (including spam, GEL prices, comparables, and a flip deal) to JSON
    export_data = [
        # 5 Clean Toyota Prius comparables around $4,950 - $5,200
        {
            "source_listing_id": "9001",
            "make": "Toyota",
            "model": "Prius",
            "year": 2013,
            "fuel": "ჰიბრიდი",
            "body_style": "ჰეთჩბექი",
            "drivetrain": "წინა",
            "mileage_km": 158000,
            "location": "თბილისი",
            "customs_status": "განბაჟებულია",
            "price": 4950,
            "currency": "USD",
            "description": "განბაჟებულია, კარგ მდგომარეობაში",
        },
        {
            "source_listing_id": "9002",
            "make": "Toyota",
            "model": "Prius",
            "year": 2014,
            "fuel": "Hybrid",
            "body_style": "Hatchback",
            "drivetrain": "FWD",
            "mileage_km": 149000,
            "location": "Tbilisi",
            "customs_status": "cleared",
            "price": 5100,
            "currency": "USD",
            "description": "Clean title, customs cleared",
        },
        {
            "source_listing_id": "9003",
            "make": "Toyota",
            "model": "Prius",
            "year": 2013,
            "fuel": "Hybrid",
            "body_style": "Hatchback",
            "drivetrain": "FWD",
            "mileage_km": 162000,
            "location": "Tbilisi",
            "customs_status": "cleared",
            "price": 5000,
            "currency": "USD",
            "description": "განბაჟებულია",
        },
        {
            "source_listing_id": "9004",
            "make": "Toyota",
            "model": "Prius",
            "year": 2012,
            "fuel": "Hybrid",
            "body_style": "Hatchback",
            "drivetrain": "FWD",
            "mileage_km": 171000,
            "location": "Tbilisi",
            "customs_status": "cleared",
            "price": 4900,
            "currency": "USD",
            "description": "განბაჟებულია",
        },
        {
            "source_listing_id": "9005",
            "make": "Toyota",
            "model": "Prius",
            "year": 2014,
            "fuel": "Hybrid",
            "body_style": "Hatchback",
            "drivetrain": "FWD",
            "mileage_km": 144000,
            "location": "Tbilisi",
            "customs_status": "cleared",
            "price": 5200,
            "currency": "USD",
            "description": "განბაჟებულია",
        },
        # Spam / rejected listings: $1 placeholder & parts-only
        {
            "source_listing_id": "9006_spam",
            "make": "Toyota",
            "model": "Prius",
            "year": 2013,
            "fuel": "Hybrid",
            "price": 1,
            "currency": "USD",
            "description": "ფასი შეთანხმებით",
        },
        {
            "source_listing_id": "9007_parts",
            "make": "Toyota",
            "model": "Prius",
            "year": 2013,
            "fuel": "Hybrid",
            "price": 1800,
            "currency": "USD",
            "description": "იყიდება ნაწილებად, ძრავის პრობლემა",
        },
        # Undervalued candidate deal at $3,150
        {
            "source_listing_id": "9008_deal",
            "make": "Toyota",
            "model": "Prius",
            "year": 2013,
            "fuel": "ჰიბრიდი",
            "body_style": "ჰეთჩბექი",
            "drivetrain": "წინა",
            "mileage_km": 154000,
            "location": "თბილისი",
            "customs_status": "განბაჟებულია",
            "price": 3150,
            "currency": "USD",
            "description": "სასწრაფოდ! განბაჟებულია, იდეალურ მდგომარეობაში",
        },
    ]
    json_path = tmp_path / "listings_export.json"
    json_path.write_text(json.dumps(export_data, ensure_ascii=False), encoding="utf-8")

    # Import via ListingImportAdapter and DealService
    adapter = ListingImportAdapter()
    import_res = adapter.import_from_file(json_path)
    assert import_res.status_mode == SourceStatusMode.IMPORT_ONLY
    assert len(import_res.listings) == 8

    deal_service = DealService(db=db2, settings=settings)
    evaluated = deal_service.ingest_and_evaluate_listings(import_res.listings)
    assert len(evaluated) == 8

    # 4. Simulate network failure on MyAuto live endpoint and verify SearchService falls back to persisted DB listings
    def network_err_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Simulated connection failure", request=request)

    err_client = httpx.AsyncClient(transport=httpx.MockTransport(network_err_handler))
    failing_myauto = MyAutoSource(http_client=err_client)
    search_service = SearchService(db=db2, settings=settings, source=failing_myauto)

    mock_bot = AsyncMock()
    scanned_count = await search_service.run_all_active_profiles_scheduled(bot=mock_bot)
    await err_client.aclose()

    assert scanned_count == 2
    mock_bot.send_message.assert_awaited_once()
    alert_msg = mock_bot.send_message.call_args.kwargs["text"]
    assert "9008_deal" in alert_msg or "$3,150" in alert_msg

    # Verify source health recorded the network failure accurately
    with db2.session() as session:
        d_repo = DealRepository(session)
        l_repo = ListingRepository(session)
        health = d_repo.get_source_health("myauto")
        assert health is not None
        assert health.status_mode == SourceStatusMode.TEMPORARILY_UNAVAILABLE.value
        assert len(l_repo.list_clean_listings()) == 6


def test_cli_commands_check_config_and_init_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "cli_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "123456")

    assert cli_main(["init-db"]) == 0
    assert db_path.exists()
    assert cli_main(["check-config"]) == 0
