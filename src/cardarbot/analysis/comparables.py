from __future__ import annotations

import statistics

from cardarbot.domain.deals import ComparableMatch, MarketValuationResult
from cardarbot.domain.enums import ConfidenceLevel, CustomsStatus, FuelType
from cardarbot.domain.vehicles import NormalizedListing


def _compute_quantile(sorted_prices: list[float], q: float) -> float:
    """Compute linear interpolated quantile on a non-empty sorted list of floats."""
    n = len(sorted_prices)
    if n == 1:
        return sorted_prices[0]
    pos = q * (n - 1)
    lower = int(pos)
    upper = min(lower + 1, n - 1)
    weight = pos - lower
    return sorted_prices[lower] * (1.0 - weight) + sorted_prices[upper] * weight


def select_comparables_and_estimate_value(
    candidate: NormalizedListing,
    pool: list[NormalizedListing],
    min_comparables: int = 5,
    resale_discount_percent: float = 10.0,
    max_year_delta: int = 2,
    max_mileage_delta_km: int = 75000,
) -> MarketValuationResult:
    """Select real comparable listings and calculate a conservative market valuation.

    Invariants:
    - Never invent comparables.
    - Exclude suspicious/rejected and duplicate listings.
    - Exclude the candidate itself.
    - Prefer median and conservative 25th-percentile quantiles.
    - Apply configurable resale discount so asking prices are never equated with sale prices.
    - If comparable count < min_comparables (default 5), mark as UNCERTAIN.
    """
    seen_ids: set[str] = {candidate.source_listing_id}
    seen_signatures: set[tuple[str | None, str | None, int | None, float | None, int | None]] = (
        set()
    )
    matches: list[ComparableMatch] = []

    for comp in pool:
        if comp.source_listing_id in seen_ids:
            continue
        if comp.usd_price is None or comp.usd_price < 400.0:
            continue
        if comp.condition_indicators.get("is_rejected"):
            continue

        # Must match Make & Model
        if not candidate.make or not comp.make or candidate.make.lower() != comp.make.lower():
            continue
        if not candidate.model or not comp.model or candidate.model.lower() != comp.model.lower():
            continue

        # Year tolerance
        similarity = 1.0
        if candidate.year is not None and comp.year is not None:
            yr_diff = abs(candidate.year - comp.year)
            if yr_diff > max_year_delta:
                continue
            similarity -= yr_diff * 0.08

        # Fuel match (if known)
        if (
            candidate.fuel != FuelType.UNKNOWN
            and comp.fuel != FuelType.UNKNOWN
            and candidate.fuel != comp.fuel
        ):
            continue

        # Customs status match (if known)
        if (
            candidate.customs_status != CustomsStatus.UNKNOWN
            and comp.customs_status != CustomsStatus.UNKNOWN
            and candidate.customs_status != comp.customs_status
        ):
            continue

        # Mileage tolerance (if both known)
        if candidate.mileage_km is not None and comp.mileage_km is not None:
            km_diff = abs(candidate.mileage_km - comp.mileage_km)
            if km_diff > max_mileage_delta_km:
                similarity -= 0.15
            else:
                similarity -= (km_diff / max_mileage_delta_km) * 0.08

        # Deduplicate identical reposted advertisements by signature
        sig = (comp.make, comp.model, comp.year, comp.usd_price, comp.mileage_km)
        if sig in seen_signatures:
            continue
        seen_signatures.add(sig)
        seen_ids.add(comp.source_listing_id)

        matches.append(
            ComparableMatch(
                source_listing_id=comp.source_listing_id,
                url=comp.url,
                make=comp.make,
                model=comp.model,
                year=comp.year,
                mileage_km=comp.mileage_km,
                usd_price=comp.usd_price,
                similarity_score=round(max(0.1, similarity), 2),
            )
        )

    matches.sort(key=lambda m: (-m.similarity_score, m.usd_price))
    count = len(matches)

    if count == 0:
        return MarketValuationResult(
            comparable_count=0,
            resale_discount_percent=resale_discount_percent,
            confidence=ConfidenceLevel.UNCERTAIN,
            is_uncertain=True,
            comparables=[],
            notes=["No matching comparable listings available in database."],
        )

    sorted_prices = sorted(m.usd_price for m in matches)
    median_val = round(float(statistics.median(sorted_prices)), 2)
    q25_val = round(_compute_quantile(sorted_prices, 0.25), 2)
    q75_val = round(_compute_quantile(sorted_prices, 0.75), 2)

    # Conservative anchor blends median and Q25, then applies resale discount
    conservative_anchor = (median_val * 0.6) + (q25_val * 0.4)
    discount_multiplier = max(0.5, 1.0 - (resale_discount_percent / 100.0))
    conservative_resale = round(conservative_anchor * discount_multiplier, 2)

    notes: list[str] = []
    if count < min_comparables:
        confidence = ConfidenceLevel.UNCERTAIN
        is_uncertain = True
        notes.append(
            f"Only {count} comparables found (minimum {min_comparables} required for high-confidence valuation)."
        )
    elif count >= min_comparables + 3:
        confidence = ConfidenceLevel.HIGH
        is_uncertain = False
    else:
        confidence = ConfidenceLevel.MEDIUM
        is_uncertain = False

    return MarketValuationResult(
        comparable_count=count,
        median_asking_usd=median_val,
        q25_asking_usd=q25_val,
        q75_asking_usd=q75_val,
        resale_discount_percent=resale_discount_percent,
        conservative_resale_usd=conservative_resale,
        confidence=confidence,
        is_uncertain=is_uncertain,
        comparables=matches[:10],
        notes=notes,
    )
