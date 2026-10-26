from __future__ import annotations

import logging
from typing import Any

import httpx

from cardarbot.analysis.normalization import normalize_raw_listing_dict
from cardarbot.domain.enums import (
    BodyStyle,
    CustomsFilterMode,
    Drivetrain,
    FuelType,
    OffRoadPreference,
    SourceStatusMode,
    Transmission,
)
from cardarbot.domain.search_profiles import SearchFilterConfig
from cardarbot.domain.vehicles import MANUFACTURER_CATALOG, NormalizedListing
from cardarbot.sources.base import BaseListingSource, SourceFetchResult

logger = logging.getLogger("cardarbot.sources.myauto")

# Reverse mappings from domain enums to MyAuto query parameter IDs
_BODY_TO_MYAUTO_CATS: dict[BodyStyle, list[int]] = {
    BodyStyle.SEDAN: [1],
    BodyStyle.HATCHBACK: [2],
    BodyStyle.WAGON: [3],
    BodyStyle.COUPE: [4],
    BodyStyle.SUV_CROSSOVER: [5, 66],
    BodyStyle.CONVERTIBLE: [6],
    BodyStyle.VAN: [7],
    BodyStyle.PICKUP: [29],
    BodyStyle.MINIVAN: [30],
}

_DRIVE_TO_MYAUTO_IDS: dict[Drivetrain, int] = {
    Drivetrain.FWD: 1,
    Drivetrain.RWD: 2,
    Drivetrain.AWD: 3,
    Drivetrain.FOUR_WD: 3,
}

_FUEL_TO_MYAUTO_IDS: dict[FuelType, int] = {
    FuelType.GASOLINE: 2,
    FuelType.DIESEL: 3,
    FuelType.HYBRID: 6,
    FuelType.ELECTRIC: 7,
    FuelType.CNG: 8,
    FuelType.LPG: 9,
    FuelType.PLUGIN_HYBRID: 10,
}

_GEAR_TO_MYAUTO_IDS: dict[Transmission, list[int]] = {
    Transmission.MANUAL: [1],
    Transmission.AUTOMATIC: [2, 3],
    Transmission.CVT: [4],
}


class MyAutoSource(BaseListingSource):
    """Permitted MyAuto.ge listing source adapter.

    Architectural & Compliance Notes:
    - Investigated https://www.myauto.ge/ and https://api2.myauto.ge/ka/products.
    - MyAuto.ge enforces Cloudflare Turnstile / JS Managed Challenges (`cf-mitigated: challenge`,
      HTTP 403) on automated HTTP requests.
    - Per strict project rules:
      1. Never bypass CAPTCHA or Cloudflare access restrictions.
      2. Never invent endpoints or silently substitute fake data.
      3. Accurately distinguish `LIVE`, `IMPORT_ONLY`, `TEMPORARILY_UNAVAILABLE`, and `UNSUPPORTED`.
    - When MyAuto responds with HTTP 200 JSON, this adapter normalizes the real payload.
    - When Cloudflare challenges or blocks automated requests (HTTP 403 / 503), this adapter
      reports `SourceStatusMode.TEMPORARILY_UNAVAILABLE` with a clear explanation and directs
      workflows to the ImportAdapter (`SourceStatusMode.IMPORT_ONLY`) or existing persisted database listings.
    """

    source_name = "myauto"
    BASE_API_URL = "https://api2.myauto.ge/ka/products"

    def __init__(
        self,
        gel_to_usd_rate: float = 0.3676,
        eur_to_usd_rate: float = 1.08,
        timeout_seconds: float = 12.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.gel_to_usd_rate = gel_to_usd_rate
        self.eur_to_usd_rate = eur_to_usd_rate
        self.timeout_seconds = timeout_seconds
        self._client = http_client

    def build_query_params(
        self, filters: SearchFilterConfig | None = None, page: int = 1
    ) -> dict[str, Any]:
        """Build documented MyAuto search query parameters from SearchFilterConfig."""
        params: dict[str, Any] = {
            "TypeID": 0,
            "ForRent": 0,
            "CurrencyID": 1,  # 1 = USD on MyAuto
            "Page": page,
        }
        if filters is None:
            return params

        if filters.min_price_usd:
            params["PriceFrom"] = filters.min_price_usd
        if filters.max_price_usd:
            params["PriceTo"] = filters.max_price_usd
        if filters.min_year:
            params["ProdYearFrom"] = filters.min_year
        if filters.max_year:
            params["ProdYearTo"] = filters.max_year
        if filters.location.lower() == "tbilisi":
            params["Locs"] = "2"  # Tbilisi location ID
        if filters.customs_mode == CustomsFilterMode.CLEARED_ONLY:
            params["Customs"] = 1

        man_ids: list[str] = []
        for mk in filters.makes:
            entry = MANUFACTURER_CATALOG.get(mk)
            if entry and entry.myauto_man_id:
                man_ids.append(str(entry.myauto_man_id))
        if man_ids:
            params["Mans"] = "-".join(man_ids)

        if filters.body_styles:
            cat_ids: list[str] = []
            for bs in filters.body_styles:
                for cid in _BODY_TO_MYAUTO_CATS.get(bs, []):
                    if str(cid) not in cat_ids:
                        cat_ids.append(str(cid))
            if cat_ids:
                params["Cats"] = ".".join(cat_ids)

        drive_ids: list[str] = []
        for dt in filters.drivetrains:
            did = _DRIVE_TO_MYAUTO_IDS.get(dt)
            if did and str(did) not in drive_ids:
                drive_ids.append(str(did))
        if not drive_ids and filters.off_road_preference == OffRoadPreference.AWD_4WD_REQUIRED:
            drive_ids.append("3")
        if drive_ids:
            params["DriveTypes"] = ".".join(drive_ids)

        if filters.fuels:
            fuel_ids: list[str] = []
            for ft in filters.fuels:
                fid = _FUEL_TO_MYAUTO_IDS.get(ft)
                if fid and str(fid) not in fuel_ids:
                    fuel_ids.append(str(fid))
            if fuel_ids:
                params["FuelTypes"] = ".".join(fuel_ids)

        if filters.transmissions:
            gear_ids: list[str] = []
            for tr in filters.transmissions:
                for gid in _GEAR_TO_MYAUTO_IDS.get(tr, []):
                    if str(gid) not in gear_ids:
                        gear_ids.append(str(gid))
            if gear_ids:
                params["GearTypes"] = ".".join(gear_ids)

        return params

    async def fetch_listings(
        self,
        filters: SearchFilterConfig | None = None,
        max_pages: int = 1,
    ) -> SourceFetchResult:
        """Attempt permitted HTTP fetch from MyAuto, handling Cloudflare restrictions cleanly."""
        headers = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "CarDarBot/1.0 (+https://github.com/Dav1tGegesh1dze/CarDarBot)",
        }

        close_client = False
        client = self._client
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout_seconds, headers=headers)
            close_client = True

        normalized_list: list[NormalizedListing] = []
        seen_ids: set[str] = set()
        last_status = 200

        try:
            for page in range(1, max(1, max_pages) + 1):
                params = self.build_query_params(filters=filters, page=page)
                response = await client.get(self.BASE_API_URL, params=params)
                last_status = response.status_code
                cf_mitigated = response.headers.get("cf-mitigated", "")

                if (
                    response.status_code in {401, 403, 429, 503}
                    or "challenge" in cf_mitigated.lower()
                ):
                    msg = (
                        f"MyAuto.ge blocked automated request (HTTP {response.status_code}, "
                        f"cf-mitigated={cf_mitigated or 'cloudflare'}). "
                        "Direct automated scraping is restricted by Cloudflare Turnstile; "
                        "operating in Import/Database mode without bypassing security."
                    )
                    logger.info(msg)
                    if normalized_list:
                        break
                    return SourceFetchResult(
                        source_name=self.source_name,
                        status_mode=SourceStatusMode.TEMPORARILY_UNAVAILABLE,
                        listings=[],
                        error_message=msg,
                        metadata={
                            "http_status": response.status_code,
                            "cf_mitigated": cf_mitigated,
                        },
                    )

                response.raise_for_status()
                payload = response.json()
                items = (
                    payload.get("data", {}).get("items", []) if isinstance(payload, dict) else []
                )
                if not items:
                    break

                for item in items:
                    if not isinstance(item, dict):
                        continue
                    try:
                        norm = normalize_raw_listing_dict(
                            item,
                            gel_to_usd=self.gel_to_usd_rate,
                            eur_to_usd=self.eur_to_usd_rate,
                        )
                        if norm.source_listing_id not in seen_ids:
                            seen_ids.add(norm.source_listing_id)
                            normalized_list.append(norm)
                    except Exception as item_exc:
                        logger.debug("Skipping malformed MyAuto item: %s", item_exc)

            return SourceFetchResult(
                source_name=self.source_name,
                status_mode=SourceStatusMode.LIVE,
                listings=normalized_list,
                metadata={"http_status": last_status, "count": len(normalized_list)},
            )

        except httpx.HTTPError as exc:
            msg = f"Network error communicating with MyAuto.ge: {exc}"
            logger.warning(msg)
            return SourceFetchResult(
                source_name=self.source_name,
                status_mode=SourceStatusMode.TEMPORARILY_UNAVAILABLE,
                listings=[],
                error_message=msg,
            )
        except Exception as exc:
            msg = f"Unexpected error parsing MyAuto response: {exc}"
            logger.warning(msg)
            return SourceFetchResult(
                source_name=self.source_name,
                status_mode=SourceStatusMode.TEMPORARILY_UNAVAILABLE,
                listings=[],
                error_message=msg,
            )
        finally:
            if close_client:
                await client.aclose()
