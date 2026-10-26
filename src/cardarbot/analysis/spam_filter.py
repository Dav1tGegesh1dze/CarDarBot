from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from cardarbot.domain.vehicles import NormalizedListing

# Minimum plausible advertised USD price for a running vehicle in Georgia
MIN_PLAUSIBLE_VEHICLE_PRICE_USD = 400.0


@dataclass
class SpamFilterResult:
    """Result of evaluating a listing through the layered spam and condition engine."""

    is_rejected: bool = False
    is_quarantined: bool = False
    rejection_reasons: list[str] = field(default_factory=list)
    risk_warnings: list[str] = field(default_factory=list)
    condition_indicators: dict[str, Any] = field(default_factory=dict)


# Trilingual rejection patterns: (tuple of substrings, explicit reason, indicator_key)
_REJECTION_RULES: list[tuple[tuple[str, ...], str, str]] = [
    (
        (
            "ნაწილებად",
            "იშლება",
            "დაშლილები",
            "parts only",
            "for parts",
            "parting out",
            "на запчасти",
            "разборка",
        ),
        "Parts-only or dismantling listing (ნაწილებად / parts only)",
        "parts_only",
    ),
    (
        (
            "არ იქოქება",
            "ვერ დადის",
            "does not run",
            "doesn't run",
            "non-running",
            "not running",
            "не заводится",
            "не на ходу",
        ),
        "Non-running vehicle (არ იქოქება / non-running)",
        "non_running",
    ),
    (
        (
            "ძრავის პრობლემა",
            "ძრავი დასტუკულია",
            "დასტუკული",
            "ძრავი არ ვარგა",
            "engine problem",
            "blown engine",
            "seized engine",
            "bad engine",
            "проблема с двигателем",
            "стучит двигатель",
        ),
        "Major engine problem reported (ძრავის პრობლემა)",
        "engine_problem",
    ),
    (
        (
            "კოლოფის პრობლემა",
            "კარობკის პრობლემა",
            "გადაცემათა კოლოფის პრობლემა",
            "gearbox problem",
            "transmission problem",
            "bad transmission",
            "slipping transmission",
            "проблема с коробкой",
            "коробка пинается",
        ),
        "Major gearbox/transmission problem reported (კოლოფის პრობლემა)",
        "gearbox_problem",
    ),
    (
        (
            "პირველი შენატანი",
            "წინასწარი შენატანი",
            "საწყისი შენატანი",
            "down payment",
            "down-payment",
            "downpayment only",
            "первый взнос",
            "первоначальный взнос",
        ),
        "Advertised price is down-payment only (პირველი შენატანი / down payment)",
        "down_payment_only",
    ),
    (
        (
            "მხოლოდ განვადებით",
            "ლიზინგის გადაბარება",
            "financing only",
            "lease takeover only",
            "только в рассрочку",
        ),
        "Financing or lease-takeover-only price (განვადება / financing only)",
        "financing_only",
    ),
    (
        (
            "მძიმე დაზიანებით",
            "ნაავარიები",
            "ჩაძირული",
            "major collision",
            "frame damage",
            "flood damage",
            "total loss",
            "тотал",
            "утопленник",
            "сильно битый",
        ),
        "Major collision, frame, or flood damage reported",
        "major_collision_damage",
    ),
]

_CONFLICTING_PRICE_RE = re.compile(
    r"(?:რეალური ფასი|სრული ფასი|ფასი არის|real price|full price|actual price)\s*[:=-]?\s*\$?\s*(\d{4,6})",
    re.IGNORECASE,
)


def evaluate_listing_credibility(listing: NormalizedListing) -> SpamFilterResult:
    """Evaluate a normalized listing for placeholder prices, spam, traps, and mechanical damage.

    Invariants:
    - Do not classify urgent-sale wording (`სასწრაფოდ`) alone as fraud.
    - Every rejected listing must have an explicit reason.
    - Avoid false certainty.
    """
    reasons: list[str] = []
    warnings: list[str] = []
    indicators: dict[str, Any] = dict(listing.condition_indicators or {})

    # 1. Currency & Price Plausibility Checks
    if listing.currency == "UNKNOWN":
        reasons.append("Unrecognized or unsupported currency")
        indicators["wrong_currency"] = True

    if listing.usd_price is None or listing.usd_price <= 0:
        reasons.append("Missing or non-positive USD price")
        indicators["invalid_price"] = True
    elif listing.usd_price < MIN_PLAUSIBLE_VEHICLE_PRICE_USD:
        reasons.append(
            f"Implausible placeholder price (${listing.usd_price:,.0f} USD < ${MIN_PLAUSIBLE_VEHICLE_PRICE_USD:,.0f} minimum)"
        )
        indicators["placeholder_price"] = True
    elif listing.year is not None and listing.year >= 2012 and listing.usd_price < 1200.0:
        reasons.append(
            f"Suspiciously low price (${listing.usd_price:,.0f} USD) for a {listing.year} model year vehicle"
        )
        indicators["suspicious_year_price"] = True

    # 2. Textual Analysis (Georgian, English, Russian)
    desc = (listing.description or "").strip()
    folded = desc.casefold()

    for keywords, reason_text, indicator_key in _REJECTION_RULES:
        if any(kw in folded for kw in keywords):
            reasons.append(reason_text)
            indicators[indicator_key] = True

    # 3. Check for conflicting prices in description vs advertised USD price
    if listing.usd_price is not None and desc:
        m_conflict = _CONFLICTING_PRICE_RE.search(desc)
        if m_conflict:
            mentioned_price = float(m_conflict.group(1))
            if abs(mentioned_price - listing.usd_price) >= 800.0:
                reasons.append(
                    f"Conflicting price in description (${mentioned_price:,.0f}) vs advertised (${listing.usd_price:,.0f})"
                )
                indicators["conflicting_price"] = True

    # 4. Non-fatal condition & context indicators (never reject urgent sale alone)
    if any(k in folded for k in ("სასწრაფოდ", "urgent", "срочно")):
        indicators["urgent_sale"] = True

    if any(k in folded for k in ("დაზიანებული", "damaged", "cosmetic damage", "битый")):
        indicators["reported_damage"] = True
        if "major_collision_damage" not in indicators:
            warnings.append(
                "Seller mentions minor/unspecified damage (დაზიანებული) — inspect carefully"
            )

    if any(k in folded for k in ("განვადება", "installment", "рассрочка")):
        indicators["mentions_installments"] = True
        if "down_payment_only" not in indicators and "financing_only" not in indicators:
            warnings.append("Listing mentions installment options (განვადება) — verify cash price")

    if any(k in folded for k in ("გაცვლა", "trade", "swap", "обмен")):
        indicators["open_to_trade"] = True

    is_rejected = len(reasons) > 0
    return SpamFilterResult(
        is_rejected=is_rejected,
        is_quarantined=is_rejected,
        rejection_reasons=reasons,
        risk_warnings=warnings,
        condition_indicators=indicators,
    )
