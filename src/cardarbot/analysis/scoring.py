from __future__ import annotations

from cardarbot.analysis.spam_filter import SpamFilterResult
from cardarbot.domain.deals import (
    MarketValuationResult,
    ProfitEstimateResult,
    ScoreBreakdown,
)
from cardarbot.domain.enums import CustomsStatus, DealClassification
from cardarbot.domain.vehicles import NormalizedListing


def classify_deal_score(score: int, hard_rejected: bool = False) -> DealClassification:
    """Classify a 0-100 deal score into Exceptional, Strong, Review, or Ignore."""
    if hard_rejected or score < 55:
        return DealClassification.IGNORE
    if score >= 85:
        return DealClassification.EXCEPTIONAL
    if score >= 70:
        return DealClassification.STRONG
    return DealClassification.REVIEW


def calculate_deal_score(
    listing: NormalizedListing,
    spam_result: SpamFilterResult,
    valuation: MarketValuationResult,
    profit: ProfitEstimateResult,
    min_comparables: int = 5,
    target_profit_usd: float = 500.0,
) -> ScoreBreakdown:
    """Compute a transparent 0-100 deal score with weighted components.

    Weights:
    - Market discount: 30
    - Expected profit: 25
    - Comparable quality: 20
    - Listing credibility: 15
    - Condition indicators: 10

    Invariants:
    - Hard rejection rules override the score (total_score = 0, classification = IGNORE).
    - Do not send high-confidence alerts for unsupported valuations (if comparable_count < min_comparables,
      cap total score below 70 so it enters REVIEW rather than STRONG/EXCEPTIONAL).
    """
    reasons: list[str] = []
    risks: list[str] = [
        "Mechanical condition unverified — in-person inspection required",
    ]
    risks.extend(spam_result.risk_warnings)

    if spam_result.is_rejected:
        return ScoreBreakdown(
            total_score=0,
            classification=DealClassification.IGNORE,
            hard_rejected=True,
            rejection_reasons=list(spam_result.rejection_reasons),
            reasons=[],
            risks=risks,
        )

    # 1. Market Discount (Max 30 points)
    market_pts = 0.0
    if valuation.median_asking_usd and valuation.median_asking_usd > 0 and listing.usd_price:
        discount_ratio = (
            valuation.median_asking_usd - listing.usd_price
        ) / valuation.median_asking_usd
        if discount_ratio > 0:
            # Full 30 points at >=30% below median asking price
            market_pts = min(30.0, round(discount_ratio * 100.0, 2))
            reasons.append(
                f"Below comparable asking prices ({discount_ratio * 100:.0f}% below median ${valuation.median_asking_usd:,.0f})"
            )

    # 2. Expected Profit (Max 25 points)
    profit_pts = 0.0
    if profit.net_profit_usd is not None and profit.net_profit_usd > 0:
        # 18 points at target_profit_usd ($500), scaling up to 25 points at 2x target ($1,000+)
        denom = max(300.0, target_profit_usd)
        ratio = profit.net_profit_usd / denom
        if ratio >= 2.0:
            profit_pts = 25.0
        elif ratio >= 1.0:
            profit_pts = 18.0 + (ratio - 1.0) * 7.0
        else:
            profit_pts = ratio * 18.0
        profit_pts = round(min(25.0, profit_pts), 2)
        reasons.append(
            f"Estimated net profit of ${profit.net_profit_usd:,.0f} after ${profit.total_expenses_usd:,.0f} expenses"
        )
    else:
        risks.append("Estimated net profit does not cover resale expenses and discount buffer")

    # 3. Comparable Quality (Max 20 points)
    comp_pts = 0.0
    if valuation.comparable_count > 0:
        avg_sim = sum(c.similarity_score for c in valuation.comparables) / len(
            valuation.comparables
        )
        count_factor = min(1.0, valuation.comparable_count / max(1, min_comparables))
        comp_pts = round(20.0 * count_factor * avg_sim, 2)
        if valuation.is_uncertain:
            risks.append(
                f"Resale estimate uncertain ({valuation.comparable_count}/{min_comparables} comparables)"
            )
        else:
            reasons.append(f"Backed by {valuation.comparable_count} comparable vehicles")
    else:
        risks.append("Resale estimate uncertain (no comparable listings found)")

    # 4. Listing Credibility (Max 15 points)
    cred_pts = 8.0  # Base for passing spam filter with plausible price
    reasons.append("Plausible advertised price")
    if listing.customs_status == CustomsStatus.CLEARED:
        cred_pts += 4.0
        reasons.append("Seller reports customs-cleared status")
    elif listing.customs_status == CustomsStatus.UNKNOWN:
        risks.append("Customs clearance status is unknown")
    else:
        risks.append("Vehicle is not customs-cleared (განუბაჟებელი)")

    if listing.description and len(listing.description) >= 20:
        cred_pts += 2.0
    if listing.mileage_km is not None and listing.mileage_km > 0:
        cred_pts += 1.0
    cred_pts = min(15.0, cred_pts)

    # 5. Condition Indicators (Max 10 points)
    cond_pts = 8.0
    if listing.condition_indicators.get("reported_damage"):
        cond_pts -= 5.0
    if listing.mileage_km is not None:
        if listing.mileage_km < 160000:
            cond_pts += 2.0
        elif listing.mileage_km > 250000:
            cond_pts -= 3.0
            risks.append(f"High reported mileage ({listing.mileage_km:,} km)")
    cond_pts = max(0.0, min(10.0, cond_pts))

    raw_total = int(round(market_pts + profit_pts + comp_pts + cred_pts + cond_pts))
    raw_total = max(0, min(100, raw_total))

    # Invariant: Do not send high-confidence alerts for unsupported valuations
    if valuation.is_uncertain and raw_total >= 70:
        raw_total = 68

    classification = classify_deal_score(raw_total, hard_rejected=False)

    return ScoreBreakdown(
        market_discount_points=market_pts,
        expected_profit_points=profit_pts,
        comparable_quality_points=comp_pts,
        listing_credibility_points=cred_pts,
        condition_points=cond_pts,
        total_score=raw_total,
        classification=classification,
        hard_rejected=False,
        rejection_reasons=[],
        reasons=reasons,
        risks=risks,
    )
