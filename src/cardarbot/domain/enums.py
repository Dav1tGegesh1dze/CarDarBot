from __future__ import annotations

from enum import StrEnum


class FuelType(StrEnum):
    ANY = "any"
    GASOLINE = "gasoline"
    DIESEL = "diesel"
    HYBRID = "hybrid"  # HEV
    PLUGIN_HYBRID = "plugin_hybrid"  # PHEV
    ELECTRIC = "electric"  # BEV
    LPG = "lpg"
    CNG = "cng"
    OTHER = "other"
    UNKNOWN = "unknown"


class PowertrainGroup(StrEnum):
    ALL = "all"
    EV = "ev"  # Battery-electric (BEV) only unless explicitly configured otherwise
    ICE = "ice"  # Gasoline or Diesel internal-combustion vehicles
    HYBRID = "hybrid"  # HEV
    PHEV = "phev"  # Separately selectable plug-in hybrid


class BodyStyle(StrEnum):
    ANY = "any"
    SEDAN = "sedan"
    COUPE = "coupe"
    HATCHBACK = "hatchback"
    WAGON = "wagon"
    SUV_CROSSOVER = "suv_crossover"
    PICKUP = "pickup"
    CONVERTIBLE = "convertible"
    MINIVAN = "minivan"
    VAN = "van"
    OTHER = "other"
    UNKNOWN = "unknown"


class Drivetrain(StrEnum):
    ANY = "any"
    FWD = "fwd"
    RWD = "rwd"
    AWD = "awd"
    FOUR_WD = "4wd"
    UNKNOWN = "unknown"


class OffRoadPreference(StrEnum):
    ANY = "any"
    AWD_4WD_PREFERRED = "awd_4wd_preferred"
    AWD_4WD_REQUIRED = "awd_4wd_required"
    VERIFIED_OFF_ROAD_MODEL = "verified_off_road_model"


class Transmission(StrEnum):
    ANY = "any"
    AUTOMATIC = "automatic"
    MANUAL = "manual"
    CVT = "cvt"
    OTHER = "other"
    UNKNOWN = "unknown"


class CustomsStatus(StrEnum):
    CLEARED = "cleared"
    UNCLEARED = "uncleared"
    UNKNOWN = "unknown"


class CustomsFilterMode(StrEnum):
    CLEARED_ONLY = "cleared_only"
    INCLUDE_UNCLEARED = "include_uncleared"
    ANY = "any"


class ScanFrequency(StrEnum):
    DAILY = "daily"
    EVERY_12_HOURS = "every_12_hours"
    EVERY_6_HOURS = "every_6_hours"
    MANUAL_ONLY = "manual_only"


class SourceStatusMode(StrEnum):
    LIVE = "live"
    IMPORT_ONLY = "import_only"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"
    UNSUPPORTED = "unsupported"


class DealClassification(StrEnum):
    EXCEPTIONAL = "exceptional"  # 85-100
    STRONG = "strong"  # 70-84
    REVIEW = "review"  # 55-69
    IGNORE = "ignore"  # <55 or rejected


class ConfidenceLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNCERTAIN = "uncertain"
