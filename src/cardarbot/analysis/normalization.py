from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from cardarbot.domain.enums import (
    BodyStyle,
    CustomsStatus,
    Drivetrain,
    FuelType,
    Transmission,
)
from cardarbot.domain.vehicles import (
    NormalizedListing,
    derive_powertrain_from_fuel,
    resolve_manufacturer,
    resolve_model,
)
from cardarbot.utils.currency import convert_to_usd, normalize_currency_code

# MyAuto fuel_type_id mapping
MYAUTO_FUEL_MAP: dict[int, FuelType] = {
    2: FuelType.GASOLINE,
    3: FuelType.DIESEL,
    6: FuelType.HYBRID,
    7: FuelType.ELECTRIC,
    8: FuelType.CNG,
    9: FuelType.LPG,
    10: FuelType.PLUGIN_HYBRID,
}

# MyAuto category_id / body style mapping
# Verified against live api2.myauto.ge/ka/products:
# 1 = Sedan, 2 = Hatchback, 3 = Wagon/Universal, 4 = Coupe,
# 5 = SUV / Jeep, 6 = Convertible / Cabrio, 7 = Van / Microbus,
# 29 = Pickup, 30 = Minivan, 66 = Crossover / SUV
MYAUTO_BODY_MAP: dict[int, BodyStyle] = {
    1: BodyStyle.SEDAN,
    2: BodyStyle.HATCHBACK,
    3: BodyStyle.WAGON,
    4: BodyStyle.COUPE,
    5: BodyStyle.SUV_CROSSOVER,
    6: BodyStyle.CONVERTIBLE,
    7: BodyStyle.VAN,
    29: BodyStyle.PICKUP,
    30: BodyStyle.MINIVAN,
    66: BodyStyle.SUV_CROSSOVER,
}

# Known SUV/Crossover models to guard against seller mis-categorization on MyAuto
_KNOWN_SUV_MODELS: set[str] = {
    "rav4",
    "highlander",
    "4runner",
    "land cruiser",
    "land cruiser prado",
    "c-hr",
    "x1",
    "x3",
    "x5",
    "x6",
    "gla",
    "glc",
    "gle",
    "glk",
    "ml",
    "g-class",
    "cr-v",
    "hr-v",
    "pilot",
    "tucson",
    "santa fe",
    "kona",
    "sportage",
    "sorento",
    "niro",
    "rogue",
    "x-trail",
    "juke",
    "murano",
    "pathfinder",
    "patrol",
    "qashqai",
    "tiguan",
    "touareg",
    "escape",
    "explorer",
    "ecosport",
    "forester",
    "outback",
    "crosstrek",
    "xv",
    "xv crosstrek",
    "rx",
    "nx",
    "gx",
    "lx",
    "outlander",
    "outlander sport",
    "asx",
    "pajero",
    "pajero io",
    "montero",
    "airtrek",
    "equinox",
    "trax",
    "tahoe",
    "suburban",
    "cx-3",
    "cx-5",
    "cx-7",
    "cx-9",
    "cx-30",
    "cx-50",
    "q3",
    "q5",
    "q7",
    "cayenne",
    "macan",
    "wrangler",
    "grand cherokee",
    "cherokee",
    "compass",
    "renegade",
    "liberty",
    "patriot",
    "antara",
    "encore",
    "500x",
    "countryman",
    "paceman",
    "2121 (niva)",
    "niva",
    "mountaineer",
}

# Known non-SUV passenger cars (sedans/hatchbacks) that should never be classified as SUV_CROSSOVER
_KNOWN_SEDAN_OR_HATCH_MODELS: dict[str, BodyStyle] = {
    "elantra": BodyStyle.SEDAN,
    "sonata": BodyStyle.SEDAN,
    "accent": BodyStyle.SEDAN,
    "camry": BodyStyle.SEDAN,
    "corolla": BodyStyle.SEDAN,
    "prius": BodyStyle.HATCHBACK,
    "aqua": BodyStyle.HATCHBACK,
    "prius c": BodyStyle.HATCHBACK,
    "vitz": BodyStyle.HATCHBACK,
    "yaris": BodyStyle.HATCHBACK,
    "fusion": BodyStyle.SEDAN,
    "focus": BodyStyle.SEDAN,
    "fiesta": BodyStyle.HATCHBACK,
    "cruze": BodyStyle.SEDAN,
    "volt": BodyStyle.HATCHBACK,
    "malibu": BodyStyle.SEDAN,
    "jetta": BodyStyle.SEDAN,
    "passat": BodyStyle.SEDAN,
    "cc": BodyStyle.SEDAN,
    "golf": BodyStyle.HATCHBACK,
    "civic": BodyStyle.SEDAN,
    "accord": BodyStyle.SEDAN,
    "fit": BodyStyle.HATCHBACK,
    "insight": BodyStyle.HATCHBACK,
    "tiida": BodyStyle.HATCHBACK,
    "note": BodyStyle.HATCHBACK,
    "leaf": BodyStyle.HATCHBACK,
    "sentra": BodyStyle.SEDAN,
    "altima": BodyStyle.SEDAN,
    "mazda 3": BodyStyle.SEDAN,
    "mazda 6": BodyStyle.SEDAN,
}

# MyAuto gear_type_id mapping
MYAUTO_GEAR_MAP: dict[int, Transmission] = {
    1: Transmission.MANUAL,
    2: Transmission.AUTOMATIC,
    3: Transmission.AUTOMATIC,  # Tiptronic
    4: Transmission.CVT,  # Variator
}

# MyAuto drive_type_id mapping (3 = 4x4/AWD on MyAuto)
MYAUTO_DRIVE_MAP: dict[int, Drivetrain] = {
    1: Drivetrain.FWD,
    2: Drivetrain.RWD,
    3: Drivetrain.FOUR_WD,
}

# MyAuto location_id mapping
MYAUTO_LOCATION_MAP: dict[int, str] = {
    2: "Tbilisi",
    3: "Kutaisi",
    4: "Batumi",
    7: "Poti",
    15: "Rustavi",
}


def normalize_fuel_text(raw: str | int | None) -> FuelType:
    """Normalize fuel type from MyAuto ID or trilingual (KA/EN/RU) text.

    Invariant: Never classify a hybrid as fully electric.
    """
    if raw is None:
        return FuelType.UNKNOWN
    if isinstance(raw, int) or (isinstance(raw, str) and raw.strip().isdigit()):
        return MYAUTO_FUEL_MAP.get(int(raw), FuelType.OTHER)
    folded = str(raw).strip().casefold()
    if not folded:
        return FuelType.UNKNOWN
    if any(k in folded for k in ("plug-in", "phev", "დატენვადი ჰიბრიდი", "плагин")):
        return FuelType.PLUGIN_HYBRID
    if any(k in folded for k in ("hybrid", "hev", "ჰიბრიდი", "ჰიბრიდული", "гибрид")):
        return FuelType.HYBRID
    if any(k in folded for k in ("electric", "bev", "ev", "ელექტრო", "электро")):
        return FuelType.ELECTRIC
    if any(k in folded for k in ("diesel", "დიზელი", "дизель")):
        return FuelType.DIESEL
    if any(k in folded for k in ("lpg", "თხევადი გაზი")):
        return FuelType.LPG
    if any(k in folded for k in ("cng", "ბუნებრივი გაზი")):
        return FuelType.CNG
    if any(k in folded for k in ("gasoline", "petrol", "ბენზინი", "бензин")):
        return FuelType.GASOLINE
    return FuelType.OTHER


def normalize_body_style_text(raw: str | int | None) -> BodyStyle:
    if raw is None:
        return BodyStyle.UNKNOWN
    if isinstance(raw, int) or (isinstance(raw, str) and raw.strip().isdigit()):
        return MYAUTO_BODY_MAP.get(int(raw), BodyStyle.OTHER)
    folded = str(raw).strip().casefold()
    if not folded:
        return BodyStyle.UNKNOWN
    if any(k in folded for k in ("sedan", "სედანი", "седан")):
        return BodyStyle.SEDAN
    if any(k in folded for k in ("coupe", "კუპე", "купе")):
        return BodyStyle.COUPE
    if any(k in folded for k in ("hatchback", "ჰეთჩბექი", "хэтчбек")):
        return BodyStyle.HATCHBACK
    if any(k in folded for k in ("wagon", "უნივერსალი", "универсал")):
        return BodyStyle.WAGON
    if any(k in folded for k in ("suv", "crossover", "ჯიპი", "კროსოვერი", "внедорожник")):
        return BodyStyle.SUV_CROSSOVER
    if any(k in folded for k in ("pickup", "პიკაპი", "пикап")):
        return BodyStyle.PICKUP
    if any(k in folded for k in ("convertible", "cabrio", "კაბრიოლეტი", "кабриолет")):
        return BodyStyle.CONVERTIBLE
    if any(k in folded for k in ("minivan", "მინივენი", "минивэн")):
        return BodyStyle.MINIVAN
    if any(k in folded for k in ("van", "ფურგონი", "фургон")):
        return BodyStyle.VAN
    return BodyStyle.OTHER


def normalize_drivetrain_text(raw: str | int | None) -> Drivetrain:
    if raw is None:
        return Drivetrain.UNKNOWN
    if isinstance(raw, int) or (isinstance(raw, str) and raw.strip().isdigit()):
        return MYAUTO_DRIVE_MAP.get(int(raw), Drivetrain.UNKNOWN)
    folded = str(raw).strip().casefold()
    if any(k in folded for k in ("4wd", "4x4", "ოთხივე")):
        return Drivetrain.FOUR_WD
    if any(k in folded for k in ("awd", "კვადრო", "სრული", "полный")):
        return Drivetrain.AWD
    if any(k in folded for k in ("fwd", "front", "წინა", "передний")):
        return Drivetrain.FWD
    if any(k in folded for k in ("rwd", "rear", "უკანა", "задний")):
        return Drivetrain.RWD
    return Drivetrain.UNKNOWN


def normalize_transmission_text(raw: str | int | None) -> Transmission:
    if raw is None:
        return Transmission.UNKNOWN
    if isinstance(raw, int) or (isinstance(raw, str) and raw.strip().isdigit()):
        return MYAUTO_GEAR_MAP.get(int(raw), Transmission.OTHER)
    folded = str(raw).strip().casefold()
    if any(k in folded for k in ("cvt", "ვარიატორი", "вариатор")):
        return Transmission.CVT
    if any(k in folded for k in ("manual", "მექანიკა", "механика")):
        return Transmission.MANUAL
    if any(k in folded for k in ("auto", "tiptronic", "ავტომატიკა", "ტიპტრონიკი", "автомат")):
        return Transmission.AUTOMATIC
    return Transmission.OTHER


def normalize_customs_status(
    raw: str | int | bool | None, description: str | None = None
) -> CustomsStatus:
    """Normalize customs status. Unknown customs status is never treated as confirmed cleared."""
    if isinstance(raw, bool):
        return CustomsStatus.CLEARED if raw else CustomsStatus.UNCLEARED
    if isinstance(raw, int):
        if raw == 1:
            return CustomsStatus.CLEARED
        if raw == 0:
            return CustomsStatus.UNCLEARED
    if isinstance(raw, str) and raw.strip():
        folded = raw.strip().casefold()
        if folded in {"1", "true", "cleared", "yes", "განბაჟებული", "განბაჟებულია", "растаможен"}:
            return CustomsStatus.CLEARED
        if folded in {"0", "false", "uncleared", "no", "განუბაჟებელი", "нерастаможен"}:
            return CustomsStatus.UNCLEARED

    if description:
        desc_folded = description.casefold()
        if "განუბაჟებელი" in desc_folded or "нерастаможен" in desc_folded:
            return CustomsStatus.UNCLEARED
        if (
            "განბაჟებულია" in desc_folded
            or "განბაჟებული" in desc_folded
            or "растаможен" in desc_folded
        ):
            return CustomsStatus.CLEARED

    return CustomsStatus.UNKNOWN


def normalize_mileage_to_km(
    raw_mileage: int | float | str | None,
    unit: str | None = None,
) -> int | None:
    """Normalize mileage from kilometers or miles into integer kilometers."""
    if raw_mileage is None:
        return None
    is_miles = False
    if unit and any(k in unit.casefold() for k in ("mi", "mile", "მილი")):
        is_miles = True
    if isinstance(raw_mileage, str):
        cleaned = raw_mileage.strip().casefold()
        if not cleaned:
            return None
        if any(k in cleaned for k in ("mi", "mile", "მილი")):
            is_miles = True
        digits = re.findall(r"\d+", cleaned)
        if not digits:
            return None
        val = int("".join(digits))
    else:
        val = int(raw_mileage)

    if val < 0:
        return None
    if is_miles:
        return int(round(val * 1.60934))
    return val


def normalize_location_text(raw: str | int | None) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, int) or (isinstance(raw, str) and raw.strip().isdigit()):
        return MYAUTO_LOCATION_MAP.get(int(raw), f"Location #{raw}")
    folded = str(raw).strip().casefold()
    if not folded:
        return None
    if any(k in folded for k in ("tbilisi", "თბილისი", "тбилиси")):
        return "Tbilisi"
    if any(k in folded for k in ("rustavi", "რუსთავი", "рустави")):
        return "Rustavi"
    if any(k in folded for k in ("batumi", "ბათუმი", "батуми")):
        return "Batumi"
    if any(k in folded for k in ("kutaisi", "ქუთაისი", "кутаиси")):
        return "Kutaisi"
    if any(k in folded for k in ("poti", "ფოთი", "поти")):
        return "Poti"
    return str(raw).strip()


def refine_body_style_with_model(
    body_style: BodyStyle,
    make: str | None,
    model: str | None,
) -> BodyStyle:
    """Refine or correct body style using known vehicle model classifications."""
    if not model:
        return body_style
    m_folded = model.strip().casefold()
    # If model is a known SUV/Crossover and raw body style was OTHER, UNKNOWN, or mis-tagged
    if m_folded in _KNOWN_SUV_MODELS:
        return BodyStyle.SUV_CROSSOVER
    # If model is a known sedan/hatchback, prevent it from ever being mislabeled as SUV_CROSSOVER
    if m_folded in _KNOWN_SEDAN_OR_HATCH_MODELS and body_style in {
        BodyStyle.SUV_CROSSOVER,
        BodyStyle.OTHER,
        BodyStyle.UNKNOWN,
    }:
        return _KNOWN_SEDAN_OR_HATCH_MODELS[m_folded]
    return body_style


def normalize_raw_listing_dict(
    raw: dict[str, Any],
    gel_to_usd: float = 0.3676,
    eur_to_usd: float = 1.08,
) -> NormalizedListing:
    """Convert a raw dictionary (from MyAuto JSON API or user import file) into a NormalizedListing."""
    listing_id = str(
        raw.get("source_listing_id")
        or raw.get("car_id")
        or raw.get("id")
        or raw.get("listing_id")
        or ""
    ).strip()
    if not listing_id:
        raise ValueError("Listing dictionary is missing source_listing_id / car_id / id")

    source = str(raw.get("source") or "myauto").strip().lower()
    url = str(raw.get("url") or f"https://www.myauto.ge/ka/pr/{listing_id}").strip()

    raw_make = raw.get("make") or raw.get("man_name") or raw.get("manufacturer")
    make = resolve_manufacturer(str(raw_make)) if raw_make else None

    raw_model = raw.get("model") or raw.get("model_name")
    model = resolve_model(make, str(raw_model)) if raw_model else None

    year_raw = raw.get("year") or raw.get("prod_year")
    year = int(year_raw) if year_raw is not None and str(year_raw).strip().isdigit() else None

    fuel = normalize_fuel_text(raw.get("fuel") or raw.get("fuel_type_id") or raw.get("fuel_type"))
    powertrain = str(raw.get("powertrain") or derive_powertrain_from_fuel(fuel))

    body_style = refine_body_style_with_model(
        normalize_body_style_text(
            raw.get("body_style") or raw.get("category_id") or raw.get("body")
        ),
        make=make,
        model=model,
    )
    drivetrain = normalize_drivetrain_text(
        raw.get("drivetrain") or raw.get("drive_type_id") or raw.get("drive")
    )
    transmission = normalize_transmission_text(
        raw.get("transmission") or raw.get("gear_type_id") or raw.get("gearbox")
    )

    mileage_km = normalize_mileage_to_km(
        raw.get("mileage_km")
        if "mileage_km" in raw
        else (raw.get("mileage") or raw.get("car_run_km") or raw.get("car_run")),
        unit=raw.get("mileage_unit"),
    )

    location = normalize_location_text(
        raw.get("location") or raw.get("location_id") or raw.get("city")
    )
    description = str(raw.get("description") or raw.get("car_desc") or "").strip() or None

    customs_raw = (
        raw.get("customs_status") if "customs_status" in raw else raw.get("customs_passed")
    )
    customs_status = normalize_customs_status(customs_raw, description=description)

    currency_raw = raw.get("currency") or ("USD" if "price_usd" in raw else "USD")
    currency = normalize_currency_code(str(currency_raw))

    price_val: float | None = None
    if raw.get("price") is not None and str(raw.get("price")).strip() != "":
        price_val = float(raw["price"])
    elif raw.get("price_usd") is not None and str(raw.get("price_usd")).strip() != "":
        price_val = float(raw["price_usd"])
        currency = "USD"
    elif raw.get("price_value") is not None:
        price_val = float(raw["price_value"])

    usd_price_explicit = raw.get("usd_price") or raw.get("price_usd")
    if usd_price_explicit is not None and str(usd_price_explicit).strip() != "":
        usd_price = round(float(usd_price_explicit), 2)
    else:
        usd_price = convert_to_usd(
            price_val,
            currency,
            gel_to_usd=gel_to_usd,
            eur_to_usd=eur_to_usd,
        )

    photos_raw = raw.get("photo_urls") or raw.get("photos") or []
    photo_urls = [str(p) for p in photos_raw] if isinstance(photos_raw, list) else []

    pub_date: datetime | None = None
    if isinstance(raw.get("publication_date"), datetime):
        pub_date = raw["publication_date"]
    elif isinstance(raw.get("publication_date"), str) and raw["publication_date"].strip():
        try:
            pub_date = datetime.fromisoformat(raw["publication_date"].replace("Z", "+00:00"))
        except ValueError:
            pub_date = None

    return NormalizedListing(
        source=source,
        source_listing_id=listing_id,
        url=url,
        make=make,
        model=model,
        generation=raw.get("generation"),
        trim=raw.get("trim"),
        year=year,
        fuel=fuel,
        powertrain=powertrain,
        body_style=body_style,
        drivetrain=drivetrain,
        transmission=transmission,
        engine=str(raw["engine"]) if raw.get("engine") else None,
        mileage_km=mileage_km,
        location=location,
        customs_status=customs_status,
        price=price_val,
        currency=currency,
        usd_price=usd_price,
        description=description,
        seller_type=raw.get("seller_type"),
        condition_indicators=raw.get("condition_indicators") or {},
        photo_urls=photo_urls,
        publication_date=pub_date,
        first_seen=datetime.now(UTC),
        last_seen=datetime.now(UTC),
    )
