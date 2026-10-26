from __future__ import annotations

import csv
import io
import json
import logging
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from cardarbot.analysis.normalization import normalize_raw_listing_dict
from cardarbot.domain.enums import SourceStatusMode
from cardarbot.domain.search_profiles import SearchFilterConfig
from cardarbot.domain.vehicles import NormalizedListing
from cardarbot.sources.base import BaseListingSource, SourceFetchResult

logger = logging.getLogger("cardarbot.sources.import_adapter")


class ListingImportAdapter(BaseListingSource):
    """Functional import adapter for user-provided vehicle listings or exports (JSON, CSV, HTML).

    Used when direct automated collection from MyAuto.ge is blocked by Cloudflare challenges
    or when importing saved browser exports / batch files via CLI or Telegram file upload.
    Never invents or fabricates listings.
    """

    source_name = "import_adapter"

    def __init__(
        self,
        gel_to_usd_rate: float = 0.3676,
        eur_to_usd_rate: float = 1.08,
    ) -> None:
        self.gel_to_usd_rate = gel_to_usd_rate
        self.eur_to_usd_rate = eur_to_usd_rate

    def parse_json_content(self, content: str) -> list[NormalizedListing]:
        """Parse JSON array or MyAuto API JSON export into NormalizedListing objects."""
        data = json.loads(content)
        raw_items: list[dict[str, Any]] = []
        if isinstance(data, list):
            raw_items = [x for x in data if isinstance(x, dict)]
        elif isinstance(data, dict):
            if "items" in data and isinstance(data["items"], list):
                raw_items = data["items"]
            elif "data" in data and isinstance(data["data"], dict) and "items" in data["data"]:
                raw_items = data["data"]["items"]
            elif "listings" in data and isinstance(data["listings"], list):
                raw_items = data["listings"]
            else:
                raw_items = [data]

        results: list[NormalizedListing] = []
        for item in raw_items:
            try:
                results.append(
                    normalize_raw_listing_dict(
                        item,
                        gel_to_usd=self.gel_to_usd_rate,
                        eur_to_usd=self.eur_to_usd_rate,
                    )
                )
            except Exception as exc:
                logger.warning("Skipping invalid JSON listing row: %s", exc)
        return results

    def parse_csv_content(self, content: str) -> list[NormalizedListing]:
        """Parse CSV export into NormalizedListing objects."""
        reader = csv.DictReader(io.StringIO(content))
        results: list[NormalizedListing] = []
        for row in reader:
            cleaned_row = {k.strip(): v.strip() for k, v in row.items() if k and v is not None}
            if not cleaned_row:
                continue
            try:
                results.append(
                    normalize_raw_listing_dict(
                        cleaned_row,
                        gel_to_usd=self.gel_to_usd_rate,
                        eur_to_usd=self.eur_to_usd_rate,
                    )
                )
            except Exception as exc:
                logger.warning("Skipping invalid CSV listing row: %s", exc)
        return results

    def parse_html_content(self, content: str) -> list[NormalizedListing]:
        """Parse saved HTML page containing JSON-LD or data-listing attributes."""
        soup = BeautifulSoup(content, "html.parser")
        results: list[NormalizedListing] = []

        # 1. Check for application/ld+json vehicle blocks
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            if not script.string:
                continue
            try:
                ld_data = json.loads(script.string)
                ld_list = ld_data if isinstance(ld_data, list) else [ld_data]
                for entry in ld_list:
                    if isinstance(entry, dict) and entry.get("@type") in {
                        "Car",
                        "Vehicle",
                        "Product",
                    }:
                        offers = (
                            entry.get("offers", {}) if isinstance(entry.get("offers"), dict) else {}
                        )
                        raw_dict = {
                            "source": "myauto_html",
                            "source_listing_id": str(
                                entry.get("sku")
                                or entry.get("productID")
                                or entry.get("url", "").split("/")[-1]
                            ),
                            "url": entry.get("url") or "https://www.myauto.ge/",
                            "make": entry.get("brand", {}).get("name")
                            if isinstance(entry.get("brand"), dict)
                            else entry.get("brand"),
                            "model": entry.get("model"),
                            "year": entry.get("vehicleModelDate") or entry.get("productionDate"),
                            "fuel": entry.get("fuelType"),
                            "body_style": entry.get("bodyType"),
                            "mileage": entry.get("mileageFromOdometer", {}).get("value")
                            if isinstance(entry.get("mileageFromOdometer"), dict)
                            else entry.get("mileageFromOdometer"),
                            "price": offers.get("price"),
                            "currency": offers.get("priceCurrency", "USD"),
                            "description": entry.get("description"),
                        }
                        results.append(
                            normalize_raw_listing_dict(
                                raw_dict,
                                gel_to_usd=self.gel_to_usd_rate,
                                eur_to_usd=self.eur_to_usd_rate,
                            )
                        )
            except Exception as exc:
                logger.debug("Skipping non-vehicle JSON-LD block: %s", exc)

        # 2. Check for explicit data-listing-id cards in saved HTML
        for card in soup.find_all(attrs={"data-listing-id": True}):
            raw_dict = {
                "source": "myauto_html",
                "source_listing_id": card.get("data-listing-id"),
                "url": card.get("data-url")
                or f"https://www.myauto.ge/ka/pr/{card.get('data-listing-id')}",
                "make": card.get("data-make"),
                "model": card.get("data-model"),
                "year": card.get("data-year"),
                "fuel": card.get("data-fuel"),
                "body_style": card.get("data-body"),
                "drivetrain": card.get("data-drivetrain"),
                "transmission": card.get("data-transmission"),
                "mileage_km": card.get("data-mileage-km"),
                "location": card.get("data-location", "Tbilisi"),
                "customs_status": card.get("data-customs"),
                "price": card.get("data-price"),
                "currency": card.get("data-currency", "USD"),
                "description": card.get_text(separator=" ", strip=True),
            }
            try:
                results.append(
                    normalize_raw_listing_dict(
                        raw_dict,
                        gel_to_usd=self.gel_to_usd_rate,
                        eur_to_usd=self.eur_to_usd_rate,
                    )
                )
            except Exception as exc:
                logger.warning("Skipping malformed HTML listing card: %s", exc)

        return results

    def import_from_file(self, file_path: Path | str) -> SourceFetchResult:
        """Load and normalize listings from a local .json, .csv, or .html file."""
        path = Path(file_path)
        if not path.exists():
            return SourceFetchResult(
                source_name=self.source_name,
                status_mode=SourceStatusMode.IMPORT_ONLY,
                listings=[],
                error_message=f"File not found: {path}",
            )

        content = path.read_text(encoding="utf-8")
        suffix = path.suffix.lower()
        if suffix == ".json":
            listings = self.parse_json_content(content)
        elif suffix == ".csv":
            listings = self.parse_csv_content(content)
        elif suffix in {".html", ".htm"}:
            listings = self.parse_html_content(content)
        else:
            return SourceFetchResult(
                source_name=self.source_name,
                status_mode=SourceStatusMode.UNSUPPORTED,
                listings=[],
                error_message=f"Unsupported import file extension '{suffix}'. Use .json, .csv, or .html.",
            )

        return SourceFetchResult(
            source_name=self.source_name,
            status_mode=SourceStatusMode.IMPORT_ONLY,
            listings=listings,
            metadata={"file": str(path), "imported_count": len(listings)},
        )

    async def fetch_listings(
        self,
        filters: SearchFilterConfig | None = None,
        max_pages: int = 1,
    ) -> SourceFetchResult:
        return SourceFetchResult(
            source_name=self.source_name,
            status_mode=SourceStatusMode.IMPORT_ONLY,
            listings=[],
            metadata={"note": "Use import_from_file or parse_*_content for user-supplied exports."},
        )
