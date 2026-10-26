from __future__ import annotations

import re
from dataclasses import dataclass, field

from cardarbot.domain.enums import (
    BodyStyle,
    CustomsFilterMode,
    Drivetrain,
    FuelType,
    OffRoadPreference,
    PowertrainGroup,
)
from cardarbot.domain.search_profiles import SearchFilterConfig
from cardarbot.domain.vehicles import (
    MANUFACTURER_CATALOG,
    expand_powertrain_group,
    is_verified_off_road_vehicle,
)


@dataclass
class NaturalLanguageParseResult:
    is_confident: bool
    suggested_name: str
    filters: SearchFilterConfig
    recognized_fields: list[str] = field(default_factory=list)


_PRICE_UNDER_RE = re.compile(
    r"(?:under|below|max|up to|მდე|<\s*)\s*\$?\s*(\d[\d,]*)\s*(k)?",
    re.IGNORECASE,
)
_PRICE_RANGE_RE = re.compile(
    r"\$(\d[\d,]*)\s*(?:-|to|–)\s*\$?(\d[\d,]*)",
    re.IGNORECASE,
)
_YEAR_RANGE_RE = re.compile(r"\b(19[89]\d|20[0-2]\d)\s*(?:-|to|–)\s*(19[89]\d|20[0-2]\d)\b")
_SINGLE_YEAR_FROM_RE = re.compile(
    r"(?:from|after|since|\+)\s*(19[89]\d|20[0-2]\d)\b|\b(19[89]\d|20[0-2]\d)\+",
    re.IGNORECASE,
)


def parse_natural_language_search(
    text: str,
    default_max_price_usd: int = 5000,
    default_min_profit_usd: int = 500,
    default_min_score: int = 70,
) -> NaturalLanguageParseResult:
    """Rule-based natural language search parser supporting English and Georgian keywords.

    Does not require an external LLM API. If no meaningful automotive filter is recognized,
    marks `is_confident=False` so the caller can guide the user to the Search Creation Wizard.
    """
    raw = text.strip()
    folded = raw.casefold()
    recognized: list[str] = []

    makes: list[str] = []
    models: list[str] = []
    fuels: list[FuelType] = []
    body_styles: list[BodyStyle] = []
    drivetrains: list[Drivetrain] = []
    off_road = OffRoadPreference.ANY
    min_price = 500
    max_price = default_max_price_usd
    min_year: int | None = None
    max_year: int | None = None
    customs_mode = CustomsFilterMode.CLEARED_ONLY

    # 1. Match manufacturers & models from catalog
    for make_name, entry in MANUFACTURER_CATALOG.items():
        make_terms = [make_name.casefold()] + [a.casefold() for a in entry.aliases]
        if (
            any(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", folded) for term in make_terms)
            and make_name not in makes
        ):
            makes.append(make_name)
            recognized.append(f"Make: {make_name}")

        for model_name, model_entry in entry.models.items():
            model_terms = [model_name.casefold()] + [a.casefold() for a in model_entry.aliases]
            for term in model_terms:
                if len(term) >= 2 and re.search(rf"(?<!\w){re.escape(term)}(?!\w)", folded):
                    if model_name not in models:
                        models.append(model_name)
                        recognized.append(f"Model: {model_name}")
                    if make_name not in makes:
                        makes.append(make_name)
                        recognized.append(f"Make: {make_name}")
                    break

    # 2. Match fuel / powertrain keywords (never classify hybrid as EV)
    if any(k in folded for k in ("plug-in hybrid", "phev", "დატენვადი ჰიბრიდი")):
        fuels.append(FuelType.PLUGIN_HYBRID)
        recognized.append("Fuel: Plug-in Hybrid (PHEV)")
    elif any(k in folded for k in ("hybrid", "hev", "ჰიბრიდი", "ჰიბრიდული", "гибрид")):
        fuels.extend(expand_powertrain_group(PowertrainGroup.HYBRID))
        recognized.append("Fuel: Hybrid (HEV)")

    if any(
        re.search(rf"(?<!\w){kw}(?!\w)", folded)
        for kw in ("electric", "ev", "bev", "ელექტრო", "ელექტრომობილი", "электро")
    ):
        for f in expand_powertrain_group(PowertrainGroup.EV):
            if f not in fuels:
                fuels.append(f)
        recognized.append("Fuel: Electric (BEV)")

    if any(k in folded for k in ("diesel", "დიზელი", "дизель")) and FuelType.DIESEL not in fuels:
        fuels.append(FuelType.DIESEL)
        recognized.append("Fuel: Diesel")
    if (
        any(k in folded for k in ("gasoline", "petrol", "ბენზინი", "бензин"))
        and FuelType.GASOLINE not in fuels
    ):
        fuels.append(FuelType.GASOLINE)
        recognized.append("Fuel: Gasoline")
    if any(k in folded for k in ("lpg", "თხევადი გაზი")):
        fuels.append(FuelType.LPG)
        recognized.append("Fuel: LPG")
    if any(k in folded for k in ("cng", "ბუნებრივი გაზი")):
        fuels.append(FuelType.CNG)
        recognized.append("Fuel: CNG")

    # 3. Body styles
    body_keywords: list[tuple[tuple[str, ...], BodyStyle]] = [
        (("sedan", "sedans", "სედანი", "седан"), BodyStyle.SEDAN),
        (("coupe", "coupes", "კუპე", "купе"), BodyStyle.COUPE),
        (("suv", "suvs", "crossover", "ჯიპი", "კროსოვერი"), BodyStyle.SUV_CROSSOVER),
        (("hatchback", "ჰეთჩბექი", "хэтчбек"), BodyStyle.HATCHBACK),
        (("wagon", "უნივერსალი", " универсал"), BodyStyle.WAGON),
        (("pickup", "პიკაპი", "пикап"), BodyStyle.PICKUP),
        (("minivan", "მინივენი", "минивэн"), BodyStyle.MINIVAN),
        (("convertible", "cabrio", "კაბრიოლეტი"), BodyStyle.CONVERTIBLE),
    ]
    for terms, b_style in body_keywords:
        if any(re.search(rf"(?<!\w){re.escape(t)}(?!\w)", folded) for t in terms):
            body_styles.append(b_style)
            recognized.append(f"Body: {b_style.value}")

    # 4. Drivetrain & Off-road
    if any(k in folded for k in ("4x4", "4wd", "off-road", "offroad", "ოფროუდი")):
        drivetrains = [Drivetrain.FOUR_WD, Drivetrain.AWD]
        off_road = OffRoadPreference.AWD_4WD_REQUIRED
        recognized.append("Drivetrain: 4WD/AWD")
    elif "awd" in folded or "კვადრო" in folded:
        drivetrains = [Drivetrain.AWD]
        off_road = OffRoadPreference.AWD_4WD_PREFERRED
        recognized.append("Drivetrain: AWD")
    elif makes and models and is_verified_off_road_vehicle(makes[0], models[0]):
        off_road = OffRoadPreference.VERIFIED_OFF_ROAD_MODEL

    # 5. Price parsing
    m_range = _PRICE_RANGE_RE.search(raw)
    if m_range:
        p1 = int(m_range.group(1).replace(",", ""))
        p2 = int(m_range.group(2).replace(",", ""))
        min_price, max_price = min(p1, p2), max(p1, p2)
        recognized.append(f"Price: ${min_price:,}–${max_price:,}")
    else:
        m_under = _PRICE_UNDER_RE.search(raw)
        if m_under:
            val = int(m_under.group(1).replace(",", ""))
            if m_under.group(2) and val < 100:
                val *= 1000
            max_price = max(500, val)
            if min_price > max_price:
                min_price = 100
            recognized.append(f"Max Price: ${max_price:,}")

    # 6. Year range parsing
    m_years = _YEAR_RANGE_RE.search(raw)
    if m_years:
        y1, y2 = int(m_years.group(1)), int(m_years.group(2))
        min_year, max_year = min(y1, y2), max(y1, y2)
        recognized.append(f"Year: {min_year}–{max_year}")
    else:
        m_single_yr = _SINGLE_YEAR_FROM_RE.search(raw)
        if m_single_yr:
            yr = int(m_single_yr.group(1) or m_single_yr.group(2))
            min_year = yr
            recognized.append(f"Year: {min_year}+")

    # 7. Customs status
    if any(k in folded for k in ("განუბაჟებელი", "uncleared")):
        customs_mode = CustomsFilterMode.INCLUDE_UNCLEARED
        recognized.append("Customs: Include uncleared")
    elif any(k in folded for k in ("განბაჟებული", "cleared")):
        customs_mode = CustomsFilterMode.CLEARED_ONLY
        recognized.append("Customs: Cleared only")

    filters = SearchFilterConfig(
        makes=makes,
        models=models,
        fuels=fuels,
        body_styles=body_styles,
        drivetrains=drivetrains,
        off_road_preference=off_road,
        min_price_usd=min_price,
        max_price_usd=max_price,
        min_year=min_year,
        max_year=max_year,
        location="Tbilisi",
        customs_mode=customs_mode,
        min_profit_usd=default_min_profit_usd,
        min_deal_score=default_min_score,
    )

    is_confident = len(recognized) > 0
    return NaturalLanguageParseResult(
        is_confident=is_confident,
        suggested_name=filters.generate_auto_name(),
        filters=filters,
        recognized_fields=recognized,
    )
