from __future__ import annotations

import httpx
import pytest

from cardarbot.analysis.normalization import (
    normalize_body_style_text,
    normalize_customs_status,
    normalize_drivetrain_text,
    normalize_fuel_text,
    normalize_mileage_to_km,
    normalize_raw_listing_dict,
    normalize_transmission_text,
)
from cardarbot.database.repositories import DealRepository, ListingRepository
from cardarbot.database.session import DatabaseManager
from cardarbot.domain.enums import (
    BodyStyle,
    CustomsStatus,
    Drivetrain,
    FuelType,
    SourceStatusMode,
    Transmission,
)
from cardarbot.domain.search_profiles import SearchFilterConfig
from cardarbot.sources.import_adapter import ListingImportAdapter
from cardarbot.sources.myauto import MyAutoSource


def test_trilingual_normalization() -> None:
    assert normalize_fuel_text("ჰიბრიდი") == FuelType.HYBRID
    assert normalize_fuel_text("დატენვადი ჰიბრიდი") == FuelType.PLUGIN_HYBRID
    assert normalize_fuel_text("ელექტრო") == FuelType.ELECTRIC
    assert normalize_fuel_text(6) == FuelType.HYBRID
    assert normalize_fuel_text(7) == FuelType.ELECTRIC

    assert normalize_body_style_text("სედანი") == BodyStyle.SEDAN
    assert normalize_body_style_text("კუპე") == BodyStyle.COUPE
    assert normalize_body_style_text(5) == BodyStyle.SUV_CROSSOVER

    assert normalize_drivetrain_text("კვადრო") == Drivetrain.AWD
    assert normalize_drivetrain_text("4x4") == Drivetrain.FOUR_WD
    assert normalize_drivetrain_text(1) == Drivetrain.FWD

    assert normalize_transmission_text("ვარიატორი") == Transmission.CVT
    assert normalize_transmission_text("მექანიკა") == Transmission.MANUAL
    assert normalize_transmission_text(2) == Transmission.AUTOMATIC

    assert normalize_customs_status(1) == CustomsStatus.CLEARED
    assert normalize_customs_status(0) == CustomsStatus.UNCLEARED
    assert normalize_customs_status(None, "მანქანა განბაჟებულია") == CustomsStatus.CLEARED
    assert normalize_customs_status(None, "განუბაჟებელი") == CustomsStatus.UNCLEARED
    assert normalize_customs_status(None, "კარგ მდგომარეობაში") == CustomsStatus.UNKNOWN

    assert normalize_mileage_to_km("120,000 km") == 120000
    assert normalize_mileage_to_km("100,000 mi") == 160934
    assert normalize_mileage_to_km(85000, unit="miles") == 136794


@pytest.mark.asyncio
async def test_myauto_source_live_and_cloudflare_challenge() -> None:
    # 1. Simulate Cloudflare 403 challenge response
    def cf_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=403,
            headers={"cf-mitigated": "challenge"},
            text="Just a moment...",
        )

    cf_client = httpx.AsyncClient(transport=httpx.MockTransport(cf_handler))
    source_cf = MyAutoSource(http_client=cf_client)
    res_cf = await source_cf.fetch_listings(
        SearchFilterConfig(makes=["Toyota"], max_price_usd=5000)
    )
    await cf_client.aclose()

    assert res_cf.status_mode == SourceStatusMode.TEMPORARILY_UNAVAILABLE
    assert res_cf.listings == []
    assert "Cloudflare" in (res_cf.error_message or "")

    # 2. Simulate permitted HTTP 200 JSON payload from MyAuto
    sample_payload = {
        "data": {
            "items": [
                {
                    "car_id": 11223344,
                    "man_name": "Toyota",
                    "model_name": "Prius",
                    "prod_year": 2014,
                    "fuel_type_id": 6,
                    "category_id": 2,
                    "gear_type_id": 4,
                    "drive_type_id": 1,
                    "car_run_km": 165000,
                    "location_id": 2,
                    "customs_passed": 1,
                    "price_usd": 3800,
                    "car_desc": "სასწრაფოდ! განბაჟებულია, იდეალურ მდგომარეობაში",
                }
            ]
        }
    }

    def ok_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, json=sample_payload)

    ok_client = httpx.AsyncClient(transport=httpx.MockTransport(ok_handler))
    source_ok = MyAutoSource(http_client=ok_client)
    res_ok = await source_ok.fetch_listings()
    await ok_client.aclose()

    assert res_ok.status_mode == SourceStatusMode.LIVE
    assert len(res_ok.listings) == 1
    item = res_ok.listings[0]
    assert item.source_listing_id == "11223344"
    assert item.make == "Toyota"
    assert item.model == "Prius"
    assert item.fuel == FuelType.HYBRID
    assert item.customs_status == CustomsStatus.CLEARED
    assert item.usd_price == 3800.0


def test_import_adapter_json_csv_html_and_db_deduplication() -> None:
    adapter = ListingImportAdapter()

    json_str = """
    [
        {
            "source_listing_id": "5001",
            "make": "Toyota",
            "model": "Prius",
            "year": 2013,
            "fuel": "Hybrid",
            "body_style": "Hatchback",
            "mileage_km": 170000,
            "location": "Tbilisi",
            "customs_status": "cleared",
            "price": 3200,
            "currency": "USD"
        }
    ]
    """
    json_items = adapter.parse_json_content(json_str)
    assert len(json_items) == 1
    assert json_items[0].usd_price == 3200.0

    csv_str = (
        "source_listing_id,make,model,year,fuel,price,currency,customs_status,location\n"
        "5002,BMW,3 Series,2014,Gasoline,10000,GEL,cleared,Tbilisi\n"
    )
    csv_items = adapter.parse_csv_content(csv_str)
    assert len(csv_items) == 1
    assert csv_items[0].make == "BMW"
    assert csv_items[0].currency == "GEL"
    assert csv_items[0].usd_price == 3676.0

    html_str = """
    <html><body>
      <div data-listing-id="5003" data-make="Nissan" data-model="Leaf" data-year="2015"
           data-fuel="Electric" data-price="3900" data-currency="USD" data-customs="cleared">
        Nissan Leaf 2015 EV in Tbilisi
      </div>
    </body></html>
    """
    html_items = adapter.parse_html_content(html_str)
    assert len(html_items) == 1
    assert html_items[0].make == "Nissan"
    assert html_items[0].fuel == FuelType.ELECTRIC

    # Persist into SQLite and verify deduplication & price history
    db = DatabaseManager("sqlite:///:memory:")
    db.init_db()
    with db.session() as session:
        l_repo = ListingRepository(session)
        d_repo = DealRepository(session)

        row, is_new, _ = l_repo.upsert_listing(json_items[0])
        assert is_new is True
        assert row.usd_price == 3200.0

        # Update price to $2,950
        updated_norm = normalize_raw_listing_dict(
            {
                "source_listing_id": "5001",
                "make": "Toyota",
                "model": "Prius",
                "year": 2013,
                "price": 2950,
                "currency": "USD",
            }
        )
        row2, is_new2, drop = l_repo.upsert_listing(updated_norm)
        assert is_new2 is False
        assert row2.id == row.id
        assert drop == 250.0

        health = d_repo.update_source_health(
            "myauto", status_mode=SourceStatusMode.IMPORT_ONLY.value
        )
        assert health.status_mode == "import_only"
