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
            "ძრავს აქვს პრობლემა",
            "ძრავზე აქვს პრობლემა",
            "პრობლემა აქვს ძრავს",
            "ძრავი დასტუკულია",
            "დასტუკული",
            "ძრავი არ ვარგა",
            "მ.ატორს აქვს ხმა",
            "მატორს აქვს ხმა",
            "მატორი სტუკზეა",
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
            "პრობლემა აქვს გადაცემათა კოლოფს",
            "გადაცემათა კოლოფს აქვს პრობლემა",
            "კოლოფს აქვს პრობლემა",
            "კარობკას აქვს პრობლემა",
            "დაზიანებული სიჩქარეების გადამრთველი",
            "დაზიანებული კოლოფი",
            "დაზიანებული გადაცემათა კოლოფი",
            "პერვიჩნი",
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
            "პირველადი შენატანი",
            "წინასწარი შენატანი",
            "წინასწარი შემოსატანი",
            "საწყისი შენატანი",
            "down payment",
            "down-payment",
            "downpayment only",
            "первый взнос",
            "первоначальный взнос",
        ),
        "Advertised price is down-payment only (წინასწარი შენატანი / down payment)",
        "down_payment_only",
    ),
    (
        (
            "ლომბარდშია",
            "ლომბარდში",
            "ლომბარდი",
            "ლომბარდს",
            "გადმოგაბარებთ",
            "გადაიბარეთ",
            "გადაბარებით",
            "სესხის გადაბარება",
            "ბანკის გადაბარება",
            "ხელზე მომეცით",
            "ხელზე მინდა",
            "მხოლოდ განვადებით",
            "მხოლოდ ლიზინგით",
            "თი ჯი ლიზინგ",
            "ლიზინგის საშუალებით",
            "ლიზინგის გადაბარება",
            "financing only",
            "lease takeover",
            "loan takeover",
            "только в рассрочку",
            "в ломбарде",
        ),
        "Lombard, bank loan takeover, or leasing-only price (ლომბარდი / გადაბარება / ხელზე)",
        "financing_only",
    ),
    (
        (
            "მძიმე დაზიანებით",
            "ნაავარიები",
            "ჩაძირული",
            "დასეტყვილი",
            "major collision",
            "frame damage",
            "flood damage",
            "hail damage",
            "total loss",
            "тотал",
            "утопленник",
            "сильно битый",
        ),
        "Major collision, frame, flood, or hail damage reported",
        "major_collision_damage",
    ),
]

# Flexible regex patterns for Georgian engine/gearbox/down-payment/lombard phrasings
_ENGINE_PROBLEM_RE = re.compile(
    r"(?:ძრავ\w*|მატორ\w*)\s+(?:\w+\s+){0,2}პრობლემ|პრობლემ\w*\s+(?:\w+\s+){0,2}(?:ძრავ\w*|მატორ\w*)",
    re.IGNORECASE,
)
_GEARBOX_PROBLEM_RE = re.compile(
    r"(?:კოლოფ\w*|კარობკ\w*)\s+(?:\w+\s+){0,2}პრობლემ|პრობლემ\w*\s+(?:\w+\s+){0,3}(?:კოლოფ\w*|კარობკ\w*)",
    re.IGNORECASE,
)
_DOWN_PAYMENT_PCT_RE = re.compile(
    r"(?:შენატანი|შემოსატანი|თანამონაწილეობა)\s*\d+\s*%|(?:\b\d{1,2}\s*%\s*-?\s*დან\b)",
    re.IGNORECASE,
)
_CASH_IN_HAND_LOAN_RE = re.compile(
    r"(?:ხელზე\s*(?:\d+|მომეცით|მინდა)|(?:\d+\s*\$?\s*ხელზე))",
    re.IGNORECASE,
)

_CONFLICTING_PRICE_RE = re.compile(
    r"(?:რეალური ფასი|სრული ფასი|ფასი არის|იქნება ფასი|გავატან|real price|full price|actual price)\s*[:=-]?\s*\$?\s*(\d{4,6})|"
    r"(\d{4,6})\s*\$\s*(?:გავატან|იქნება ფასი|არის ფასი|სრული ფასი)",
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

    # 2b. Flexible regex checks for Georgian word order variations
    if desc:
        if "engine_problem" not in indicators and _ENGINE_PROBLEM_RE.search(desc):
            reasons.append("Major engine problem reported in description (ძრავის პრობლემა)")
            indicators["engine_problem"] = True
        if "gearbox_problem" not in indicators and _GEARBOX_PROBLEM_RE.search(desc):
            reasons.append(
                "Major gearbox/transmission problem reported in description (კოლოფის პრობლემა)"
            )
            indicators["gearbox_problem"] = True
        if "down_payment_only" not in indicators and _DOWN_PAYMENT_PCT_RE.search(desc):
            reasons.append("Advertised price is percentage down-payment / financing offer")
            indicators["down_payment_only"] = True
        if "financing_only" not in indicators and _CASH_IN_HAND_LOAN_RE.search(desc):
            reasons.append(
                "Advertised price is partial cash-in-hand (ხელზე) with loan/lombard balance"
            )
            indicators["financing_only"] = True

    # 3. Check for conflicting prices in description vs advertised USD price
    if listing.usd_price is not None and desc:
        m_conflict = _CONFLICTING_PRICE_RE.search(desc)
        if m_conflict:
            raw_num = m_conflict.group(1) or m_conflict.group(2)
            if raw_num:
                mentioned_price = float(raw_num)
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
