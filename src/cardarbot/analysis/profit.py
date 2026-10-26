from __future__ import annotations

from cardarbot.domain.deals import (
    ExpenseBreakdown,
    MarketValuationResult,
    ProfitEstimateResult,
)
from cardarbot.domain.enums import CustomsStatus
from cardarbot.domain.vehicles import NormalizedListing


def build_expense_breakdown(
    listing: NormalizedListing,
    default_buffer_usd: float = 400.0,
) -> ExpenseBreakdown:
    """Build an itemized expense breakdown tailored to the candidate vehicle."""
    scale = default_buffer_usd / 400.0 if default_buffer_usd > 0 else 1.0
    repairs = round(100.0 * scale, 2)
    contingency = round(60.0 * scale, 2)

    # Increase repair/contingency allowance if seller mentions minor damage or high mileage
    if listing.condition_indicators.get("reported_damage"):
        repairs += 150.0
    if listing.mileage_km is not None and listing.mileage_km > 220000:
        contingency += 75.0
    if listing.customs_status == CustomsStatus.UNCLEARED:
        # Uncleared vehicles require customs clearance outlay
        contingency += 500.0

    return ExpenseBreakdown(
        inspection_usd=round(50.0 * scale, 2),
        repairs_usd=repairs,
        maintenance_usd=round(60.0 * scale, 2),
        detailing_usd=round(50.0 * scale, 2),
        transport_usd=round(30.0 * scale, 2),
        registration_usd=round(35.0 * scale, 2),
        advertising_usd=round(15.0 * scale, 2),
        negotiation_allowance_usd=0.0,
        contingency_usd=contingency,
    )


def calculate_profit_estimate(
    listing: NormalizedListing,
    valuation: MarketValuationResult,
    min_profit_usd: float = 500.0,
    default_expense_buffer_usd: float = 400.0,
) -> ProfitEstimateResult:
    """Calculate estimated net resale profit.

    Formula:
    Estimated net profit = Conservative resale value - Asking price - Estimated expenses
    Never guarantees profit.
    """
    asking = float(listing.usd_price or 0.0)
    expenses = build_expense_breakdown(listing, default_buffer_usd=default_expense_buffer_usd)
    total_exp = expenses.total_usd

    if valuation.conservative_resale_usd is None or asking <= 0:
        return ProfitEstimateResult(
            asking_price_usd=asking,
            conservative_resale_usd=None,
            gross_spread_usd=None,
            expenses=expenses,
            total_expenses_usd=total_exp,
            net_profit_usd=None,
            return_percentage=None,
            confidence=valuation.confidence,
            meets_min_profit=False,
        )

    resale = valuation.conservative_resale_usd
    gross_spread = round(resale - asking, 2)
    net_profit = round(resale - asking - total_exp, 2)
    total_cost_basis = asking + total_exp
    roi_pct = round((net_profit / total_cost_basis) * 100.0, 2) if total_cost_basis > 0 else 0.0

    return ProfitEstimateResult(
        asking_price_usd=asking,
        conservative_resale_usd=resale,
        gross_spread_usd=gross_spread,
        expenses=expenses,
        total_expenses_usd=total_exp,
        net_profit_usd=net_profit,
        return_percentage=roi_pct,
        confidence=valuation.confidence,
        meets_min_profit=bool(net_profit >= min_profit_usd),
    )
