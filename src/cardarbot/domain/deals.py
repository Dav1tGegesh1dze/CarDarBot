from __future__ import annotations

from pydantic import BaseModel, Field

from cardarbot.domain.enums import ConfidenceLevel, DealClassification


class ExpenseBreakdown(BaseModel):
    """Itemized resale expense estimate in USD."""

    inspection_usd: float = 50.0
    repairs_usd: float = 100.0
    maintenance_usd: float = 60.0
    detailing_usd: float = 50.0
    transport_usd: float = 30.0
    registration_usd: float = 35.0
    advertising_usd: float = 15.0
    negotiation_allowance_usd: float = 0.0
    contingency_usd: float = 60.0

    @property
    def total_usd(self) -> float:
        return round(
            self.inspection_usd
            + self.repairs_usd
            + self.maintenance_usd
            + self.detailing_usd
            + self.transport_usd
            + self.registration_usd
            + self.advertising_usd
            + self.negotiation_allowance_usd
            + self.contingency_usd,
            2,
        )


class ComparableMatch(BaseModel):
    """Reference to a comparable vehicle listing used in valuation."""

    listing_id: int | None = None
    source_listing_id: str
    url: str
    make: str | None = None
    model: str | None = None
    year: int | None = None
    mileage_km: int | None = None
    usd_price: float
    similarity_score: float = 1.0


class MarketValuationResult(BaseModel):
    """Market value estimation result derived from comparable listings."""

    comparable_count: int = 0
    median_asking_usd: float | None = None
    q25_asking_usd: float | None = None
    q75_asking_usd: float | None = None
    resale_discount_percent: float = 10.0
    conservative_resale_usd: float | None = None
    confidence: ConfidenceLevel = ConfidenceLevel.UNCERTAIN
    is_uncertain: bool = True
    comparables: list[ComparableMatch] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ProfitEstimateResult(BaseModel):
    """Profit estimation breakdown for a candidate vehicle."""

    asking_price_usd: float
    conservative_resale_usd: float | None = None
    gross_spread_usd: float | None = None
    expenses: ExpenseBreakdown
    total_expenses_usd: float
    net_profit_usd: float | None = None
    return_percentage: float | None = None
    confidence: ConfidenceLevel = ConfidenceLevel.UNCERTAIN
    meets_min_profit: bool = False


class ScoreBreakdown(BaseModel):
    """Weighted 0-100 deal score breakdown."""

    market_discount_points: float = 0.0  # Max 30
    expected_profit_points: float = 0.0  # Max 25
    comparable_quality_points: float = 0.0  # Max 20
    listing_credibility_points: float = 0.0  # Max 15
    condition_points: float = 0.0  # Max 10
    total_score: int = 0
    classification: DealClassification = DealClassification.IGNORE
    hard_rejected: bool = False
    rejection_reasons: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class DealEvaluationDomain(BaseModel):
    """Full evaluation of a candidate listing against market comparables."""

    listing_id: int | None = None
    source_listing_id: str
    matched_profile_id: int | None = None
    matched_profile_name: str | None = None
    valuation: MarketValuationResult
    profit: ProfitEstimateResult
    score: ScoreBreakdown
