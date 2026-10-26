from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from cardarbot.domain.enums import (
    BodyStyle,
    CustomsStatus,
    Drivetrain,
    FuelType,
    PowertrainGroup,
    Transmission,
)


class ModelCatalogEntry(BaseModel):
    """Represents a vehicle model with aliases, source IDs, and verified off-road capability."""

    name: str
    aliases: list[str] = Field(default_factory=list)
    myauto_model_id: int | None = None
    verified_off_road: bool = False


class ManufacturerCatalogEntry(BaseModel):
    """Represents a vehicle manufacturer with its supported models and source ID."""

    name: str
    aliases: list[str] = Field(default_factory=list)
    myauto_man_id: int | None = None
    models: dict[str, ModelCatalogEntry] = Field(default_factory=dict)


# Comprehensive, searchable, maintainable manufacturer & model catalog
MANUFACTURER_CATALOG: dict[str, ManufacturerCatalogEntry] = {
    "Toyota": ManufacturerCatalogEntry(
        name="Toyota",
        aliases=["ტოიოტა", "Тойота"],
        myauto_man_id=41,
        models={
            "Prius": ModelCatalogEntry(
                name="Prius", aliases=["პრიუსი", "Приус"], myauto_model_id=1083
            ),
            "Prius C": ModelCatalogEntry(
                name="Prius C", aliases=["პრიუს ც", "პრიუს c"], myauto_model_id=1322
            ),
            "Aqua": ModelCatalogEntry(name="Aqua", aliases=["აქვა", "Акವಾ"], myauto_model_id=1450),
            "Camry": ModelCatalogEntry(
                name="Camry", aliases=["ქამრი", "კამრი", "Камри"], myauto_model_id=1044
            ),
            "Corolla": ModelCatalogEntry(
                name="Corolla", aliases=["კოროლა", "Королла"], myauto_model_id=1052
            ),
            "RAV4": ModelCatalogEntry(
                name="RAV4", aliases=["RAV 4", "რავ4", "რავ 4"], myauto_model_id=1086
            ),
            "Highlander": ModelCatalogEntry(
                name="Highlander", aliases=["ჰაილენდერი"], myauto_model_id=1063
            ),
            "C-HR": ModelCatalogEntry(
                name="C-HR", aliases=["CHR", "სი-ეიჩ-არ"], myauto_model_id=1510
            ),
            "4Runner": ModelCatalogEntry(
                name="4Runner",
                aliases=["4 Runner", "ფორრანერი"],
                myauto_model_id=1037,
                verified_off_road=True,
            ),
            "Land Cruiser": ModelCatalogEntry(
                name="Land Cruiser",
                aliases=["Land Cruiser Prado", "Prado", "ლენდ კრუიზერი", "პრადო"],
                myauto_model_id=1070,
                verified_off_road=True,
            ),
            "Hilux": ModelCatalogEntry(
                name="Hilux",
                aliases=["ჰაილუქსი"],
                myauto_model_id=1064,
                verified_off_road=True,
            ),
            "FJ Cruiser": ModelCatalogEntry(
                name="FJ Cruiser",
                aliases=["ეფჯეი კრუიზერი"],
                myauto_model_id=1059,
                verified_off_road=True,
            ),
        },
    ),
    "BMW": ManufacturerCatalogEntry(
        name="BMW",
        aliases=["ბმვ", "БМВ"],
        myauto_man_id=3,
        models={
            "3 Series": ModelCatalogEntry(
                name="3 Series",
                aliases=["320", "328", "330", "335", "E90", "F30", "მესამე სერია"],
                myauto_model_id=45,
            ),
            "5 Series": ModelCatalogEntry(
                name="5 Series",
                aliases=["520", "528", "530", "535", "550", "E60", "F10", "მეხუთე სერია"],
                myauto_model_id=57,
            ),
            "7 Series": ModelCatalogEntry(
                name="7 Series", aliases=["740", "750", "მეშვიდე სერია"], myauto_model_id=66
            ),
            "X1": ModelCatalogEntry(name="X1", aliases=["იქს1"], myauto_model_id=1210),
            "X3": ModelCatalogEntry(name="X3", aliases=["იქს3"], myauto_model_id=76),
            "X5": ModelCatalogEntry(name="X5", aliases=["იქს5"], myauto_model_id=77),
            "i3": ModelCatalogEntry(name="i3", aliases=["აი3"], myauto_model_id=1412),
            "i4": ModelCatalogEntry(name="i4", aliases=["აი4"], myauto_model_id=1890),
        },
    ),
    "Mercedes-Benz": ManufacturerCatalogEntry(
        name="Mercedes-Benz",
        aliases=["Mercedes", "მერსედესი", "მერსედეს-ბენცი", "Мерседес"],
        myauto_man_id=25,
        models={
            "C-Class": ModelCatalogEntry(
                name="C-Class",
                aliases=["C Class", "C200", "C250", "C300", "W204", "W205", "ც კლასი"],
                myauto_model_id=580,
            ),
            "E-Class": ModelCatalogEntry(
                name="E-Class",
                aliases=["E Class", "E200", "E300", "E350", "W211", "W212", "ე კლასი"],
                myauto_model_id=601,
            ),
            "S-Class": ModelCatalogEntry(
                name="S-Class", aliases=["S Class", "S500", "S550", "ს კლასი"], myauto_model_id=645
            ),
            "GLA": ModelCatalogEntry(name="GLA", aliases=["GLA 250"], myauto_model_id=1430),
            "GLC": ModelCatalogEntry(name="GLC", aliases=["GLC 300"], myauto_model_id=1550),
            "GLE": ModelCatalogEntry(name="GLE", aliases=["ML", "GLE 350"], myauto_model_id=1551),
            "G-Class": ModelCatalogEntry(
                name="G-Class",
                aliases=["G Class", "Geländewagen", "G500", "G55", "G63", "ჯი კლასი"],
                myauto_model_id=615,
                verified_off_road=True,
            ),
        },
    ),
    "Honda": ManufacturerCatalogEntry(
        name="Honda",
        aliases=["ჰონდა", "Хонდა"],
        myauto_man_id=12,
        models={
            "Fit": ModelCatalogEntry(
                name="Fit", aliases=["Jazz", "ფიტი", "ჯაზი"], myauto_model_id=312
            ),
            "Civic": ModelCatalogEntry(name="Civic", aliases=["სივიკი"], myauto_model_id=301),
            "CR-V": ModelCatalogEntry(
                name="CR-V", aliases=["CRV", "ცრვ", "სი-არ-ვი"], myauto_model_id=305
            ),
            "Insight": ModelCatalogEntry(name="Insight", aliases=["ინსაითი"], myauto_model_id=318),
            "Accord": ModelCatalogEntry(name="Accord", aliases=["აკორდი"], myauto_model_id=295),
            "HR-V": ModelCatalogEntry(name="HR-V", aliases=["HRV"], myauto_model_id=315),
        },
    ),
    "Hyundai": ManufacturerCatalogEntry(
        name="Hyundai",
        aliases=["ჰიუნდაი", "Хендай"],
        myauto_man_id=14,
        models={
            "Elantra": ModelCatalogEntry(name="Elantra", aliases=["ელანტრა"], myauto_model_id=350),
            "Sonata": ModelCatalogEntry(name="Sonata", aliases=["სონატა"], myauto_model_id=365),
            "Tucson": ModelCatalogEntry(name="Tucson", aliases=["ტუქსონი"], myauto_model_id=370),
            "Santa Fe": ModelCatalogEntry(
                name="Santa Fe", aliases=["სანტა ფე"], myauto_model_id=362
            ),
            "Ioniq": ModelCatalogEntry(name="Ioniq", aliases=["აიონიკი"], myauto_model_id=1580),
            "Kona": ModelCatalogEntry(name="Kona", aliases=["კონა"], myauto_model_id=1620),
        },
    ),
    "Kia": ManufacturerCatalogEntry(
        name="Kia",
        aliases=["კია", "Киа"],
        myauto_man_id=19,
        models={
            "Optima": ModelCatalogEntry(
                name="Optima", aliases=["K5", "ოპტიმა"], myauto_model_id=450
            ),
            "Forte": ModelCatalogEntry(
                name="Forte", aliases=["Cerato", "ფორტე"], myauto_model_id=445
            ),
            "Sportage": ModelCatalogEntry(
                name="Sportage", aliases=["სპორტეიჯი"], myauto_model_id=460
            ),
            "Sorento": ModelCatalogEntry(name="Sorento", aliases=["სორენტო"], myauto_model_id=458),
            "Soul": ModelCatalogEntry(name="Soul", aliases=["სოული"], myauto_model_id=459),
            "Niro": ModelCatalogEntry(name="Niro", aliases=["ნირო"], myauto_model_id=1590),
        },
    ),
    "Nissan": ManufacturerCatalogEntry(
        name="Nissan",
        aliases=["ნისანი", "Ниссан"],
        myauto_man_id=30,
        models={
            "Leaf": ModelCatalogEntry(name="Leaf", aliases=["ლიფი", "Лиф"], myauto_model_id=1280),
            "Juke": ModelCatalogEntry(name="Juke", aliases=["ჯუკი"], myauto_model_id=1275),
            "Rogue": ModelCatalogEntry(
                name="Rogue", aliases=["X-Trail", "როგი", "იქს-ტრეილი"], myauto_model_id=765
            ),
            "Tiida": ModelCatalogEntry(
                name="Tiida", aliases=["Versa", "ტიდა"], myauto_model_id=775
            ),
            "Note": ModelCatalogEntry(name="Note", aliases=["ნოუთი"], myauto_model_id=750),
            "Patrol": ModelCatalogEntry(
                name="Patrol",
                aliases=["პატრული"],
                myauto_model_id=755,
                verified_off_road=True,
            ),
            "Xterra": ModelCatalogEntry(
                name="Xterra",
                aliases=["იქსტერა"],
                myauto_model_id=780,
                verified_off_road=True,
            ),
        },
    ),
    "Volkswagen": ManufacturerCatalogEntry(
        name="Volkswagen",
        aliases=["VW", "ფოლკსვაგენი", "ვოლკსვაგენი", "Фольксваген"],
        myauto_man_id=42,
        models={
            "Jetta": ModelCatalogEntry(name="Jetta", aliases=["ჯეტა"], myauto_model_id=1115),
            "Passat": ModelCatalogEntry(name="Passat", aliases=["პასატი"], myauto_model_id=1120),
            "Golf": ModelCatalogEntry(
                name="Golf", aliases=["e-Golf", "გოლფი"], myauto_model_id=1110
            ),
            "Tiguan": ModelCatalogEntry(name="Tiguan", aliases=["ტიგუანი"], myauto_model_id=1135),
            "Touareg": ModelCatalogEntry(name="Touareg", aliases=["ტუარეგი"], myauto_model_id=1136),
            "ID.4": ModelCatalogEntry(name="ID.4", aliases=["ID4"], myauto_model_id=1910),
        },
    ),
    "Ford": ManufacturerCatalogEntry(
        name="Ford",
        aliases=["ფორდი", "Форд"],
        myauto_man_id=10,
        models={
            "Fusion": ModelCatalogEntry(
                name="Fusion", aliases=["Mondeo", "ფიუჟენი"], myauto_model_id=240
            ),
            "Focus": ModelCatalogEntry(name="Focus", aliases=["ფოკუსი"], myauto_model_id=235),
            "Escape": ModelCatalogEntry(
                name="Escape", aliases=["Kuga", "ესკეიპი"], myauto_model_id=230
            ),
            "Explorer": ModelCatalogEntry(
                name="Explorer", aliases=["ექსპლორერი"], myauto_model_id=232
            ),
            "Mustang": ModelCatalogEntry(name="Mustang", aliases=["მუსტანგი"], myauto_model_id=245),
            "F-150": ModelCatalogEntry(
                name="F-150",
                aliases=["F150", "Raptor"],
                myauto_model_id=233,
                verified_off_road=True,
            ),
            "Bronco": ModelCatalogEntry(
                name="Bronco",
                aliases=["ბრონკო"],
                myauto_model_id=1850,
                verified_off_road=True,
            ),
        },
    ),
    "Subaru": ManufacturerCatalogEntry(
        name="Subaru",
        aliases=["სუბარუ", "Субару"],
        myauto_man_id=39,
        models={
            "Forester": ModelCatalogEntry(
                name="Forester",
                aliases=["ფორესტერი"],
                myauto_model_id=1001,
                verified_off_road=True,
            ),
            "Outback": ModelCatalogEntry(
                name="Outback",
                aliases=["აუთბექი"],
                myauto_model_id=1008,
                verified_off_road=True,
            ),
            "XV": ModelCatalogEntry(
                name="XV",
                aliases=["Crosstrek", "ქროსტრეკი"],
                myauto_model_id=1340,
                verified_off_road=True,
            ),
            "Impreza": ModelCatalogEntry(name="Impreza", aliases=["იმპრეზა"], myauto_model_id=1003),
            "Legacy": ModelCatalogEntry(name="Legacy", aliases=["ლეგასი"], myauto_model_id=1005),
        },
    ),
    "Lexus": ManufacturerCatalogEntry(
        name="Lexus",
        aliases=["ლექსუსი", "Лексус"],
        myauto_man_id=23,
        models={
            "CT 200h": ModelCatalogEntry(
                name="CT 200h", aliases=["CT200h", "CT 200", "CT"], myauto_model_id=1290
            ),
            "RX": ModelCatalogEntry(
                name="RX", aliases=["RX 350", "RX 400h", "RX 450h"], myauto_model_id=525
            ),
            "NX": ModelCatalogEntry(
                name="NX", aliases=["NX 200t", "NX 300h"], myauto_model_id=1440
            ),
            "ES": ModelCatalogEntry(name="ES", aliases=["ES 300h", "ES 350"], myauto_model_id=510),
            "IS": ModelCatalogEntry(name="IS", aliases=["IS 250", "IS 300"], myauto_model_id=518),
            "GX": ModelCatalogEntry(
                name="GX",
                aliases=["GX 460", "GX 470"],
                myauto_model_id=515,
                verified_off_road=True,
            ),
            "LX": ModelCatalogEntry(
                name="LX",
                aliases=["LX 470", "LX 570"],
                myauto_model_id=520,
                verified_off_road=True,
            ),
        },
    ),
    "Mitsubishi": ManufacturerCatalogEntry(
        name="Mitsubishi",
        aliases=["მიცუბიში", "Митсубиси"],
        myauto_man_id=28,
        models={
            "Outlander": ModelCatalogEntry(
                name="Outlander", aliases=["Outlander Sport", "აუთლენდერი"], myauto_model_id=701
            ),
            "Pajero": ModelCatalogEntry(
                name="Pajero",
                aliases=["Montero", "Pajero IO", "პაჯერო"],
                myauto_model_id=705,
                verified_off_road=True,
            ),
            "L200": ModelCatalogEntry(
                name="L200",
                aliases=["Triton"],
                myauto_model_id=695,
                verified_off_road=True,
            ),
            "Colt": ModelCatalogEntry(name="Colt", aliases=["კოლტი"], myauto_model_id=685),
        },
    ),
    "Chevrolet": ManufacturerCatalogEntry(
        name="Chevrolet",
        aliases=["Chevy", "შევროლე", "Шевроле"],
        myauto_man_id=5,
        models={
            "Volt": ModelCatalogEntry(name="Volt", aliases=["ვოლტი"], myauto_model_id=1260),
            "Bolt": ModelCatalogEntry(
                name="Bolt", aliases=["Bolt EV", "ბოლტი"], myauto_model_id=1560
            ),
            "Cruze": ModelCatalogEntry(name="Cruze", aliases=["კრუზი"], myauto_model_id=118),
            "Malibu": ModelCatalogEntry(name="Malibu", aliases=["მალიბუ"], myauto_model_id=125),
            "Equinox": ModelCatalogEntry(
                name="Equinox", aliases=["ექუინოქსი"], myauto_model_id=120
            ),
            "Camaro": ModelCatalogEntry(name="Camaro", aliases=["კამარო"], myauto_model_id=115),
        },
    ),
    "Mazda": ManufacturerCatalogEntry(
        name="Mazda",
        aliases=["მაზდა", "Мазда"],
        myauto_man_id=24,
        models={
            "Mazda3": ModelCatalogEntry(
                name="Mazda3", aliases=["Mazda 3", "Axela", "მაზდა 3"], myauto_model_id=550
            ),
            "Mazda6": ModelCatalogEntry(
                name="Mazda6", aliases=["Mazda 6", "Atenza", "მაზდა 6"], myauto_model_id=555
            ),
            "CX-5": ModelCatalogEntry(name="CX-5", aliases=["CX5", "CX 5"], myauto_model_id=1310),
            "CX-3": ModelCatalogEntry(name="CX-3", aliases=["CX3"], myauto_model_id=1490),
            "CX-9": ModelCatalogEntry(name="CX-9", aliases=["CX9"], myauto_model_id=545),
            "Demio": ModelCatalogEntry(
                name="Demio", aliases=["Mazda2", "დემიო"], myauto_model_id=548
            ),
        },
    ),
    "Audi": ManufacturerCatalogEntry(
        name="Audi",
        aliases=["აუდი", "Ауди"],
        myauto_man_id=2,
        models={
            "A4": ModelCatalogEntry(name="A4", aliases=["ა4"], myauto_model_id=18),
            "A5": ModelCatalogEntry(name="A5", aliases=["ა5"], myauto_model_id=19),
            "A6": ModelCatalogEntry(name="A6", aliases=["ა6"], myauto_model_id=20),
            "Q5": ModelCatalogEntry(name="Q5", aliases=["ქიუ5"], myauto_model_id=28),
            "Q7": ModelCatalogEntry(name="Q7", aliases=["ქიუ7"], myauto_model_id=29),
            "e-tron": ModelCatalogEntry(name="e-tron", aliases=["etron"], myauto_model_id=1750),
        },
    ),
    "Porsche": ManufacturerCatalogEntry(
        name="Porsche",
        aliases=["პორშე", "Порше"],
        myauto_man_id=33,
        models={
            "Cayenne": ModelCatalogEntry(name="Cayenne", aliases=["კაიენი"], myauto_model_id=850),
            "Macan": ModelCatalogEntry(name="Macan", aliases=["მაკანი"], myauto_model_id=1420),
            "Panamera": ModelCatalogEntry(
                name="Panamera", aliases=["პანამერა"], myauto_model_id=855
            ),
            "911": ModelCatalogEntry(name="911", aliases=["Carrera"], myauto_model_id=845),
            "Taycan": ModelCatalogEntry(name="Taycan", aliases=["ტაიკანი"], myauto_model_id=1810),
        },
    ),
    "Jeep": ManufacturerCatalogEntry(
        name="Jeep",
        aliases=["ჯიპი", "Джип"],
        myauto_man_id=18,
        models={
            "Wrangler": ModelCatalogEntry(
                name="Wrangler",
                aliases=["Rubicon", "რენგლერი"],
                myauto_model_id=425,
                verified_off_road=True,
            ),
            "Grand Cherokee": ModelCatalogEntry(
                name="Grand Cherokee",
                aliases=["გრანდ ჩეროკი"],
                myauto_model_id=420,
                verified_off_road=True,
            ),
            "Cherokee": ModelCatalogEntry(
                name="Cherokee",
                aliases=["ჩეროკი"],
                myauto_model_id=418,
                verified_off_road=True,
            ),
            "Compass": ModelCatalogEntry(name="Compass", aliases=["კომპასი"], myauto_model_id=419),
            "Renegade": ModelCatalogEntry(
                name="Renegade", aliases=["რენეგეიდი"], myauto_model_id=1460
            ),
        },
    ),
}


def resolve_manufacturer(query: str | None) -> str | None:
    """Resolve manufacturer name or alias to canonical catalog name."""
    if not query or query.strip().lower() in {"any", "all", "*"}:
        return None
    cleaned = query.strip().lower()
    for canonical, entry in MANUFACTURER_CATALOG.items():
        if canonical.lower() == cleaned:
            return canonical
        for alias in entry.aliases:
            if alias.lower() == cleaned:
                return canonical
    # Allow custom manufacturer if not in catalog, title-cased
    return query.strip()


def resolve_model(make: str | None, model_query: str | None) -> str | None:
    """Resolve model name or alias within a manufacturer to its canonical model name."""
    if not model_query or model_query.strip().lower() in {"any", "any model", "all", "*"}:
        return None
    cleaned_model = model_query.strip().lower()
    if make:
        canonical_make = resolve_manufacturer(make)
        entry = MANUFACTURER_CATALOG.get(canonical_make or "")
        if entry:
            for model_name, model_entry in entry.models.items():
                if model_name.lower() == cleaned_model:
                    return model_name
                for alias in model_entry.aliases:
                    if alias.lower() == cleaned_model:
                        return model_name
    # Search across all manufacturers if make was Any or not matched
    for entry in MANUFACTURER_CATALOG.values():
        for model_name, model_entry in entry.models.items():
            if model_name.lower() == cleaned_model:
                return model_name
            for alias in model_entry.aliases:
                if alias.lower() == cleaned_model:
                    return model_name
    return model_query.strip()


def validate_make_model_combination(make: str | None, model: str | None) -> bool:
    """Validate whether a model belongs to the selected manufacturer."""
    if not make or make.lower() == "any" or not model or model.lower() in {"any", "any model"}:
        return True
    canonical_make = resolve_manufacturer(make)
    if not canonical_make or canonical_make not in MANUFACTURER_CATALOG:
        # Custom/"Other" manufacturer allows custom model
        return True
    entry = MANUFACTURER_CATALOG[canonical_make]
    cleaned_model = model.strip().lower()
    for model_name, model_entry in entry.models.items():
        if model_name.lower() == cleaned_model:
            return True
        if any(alias.lower() == cleaned_model for alias in model_entry.aliases):
            return True
    return False


def is_verified_off_road_vehicle(make: str | None, model: str | None) -> bool:
    """Determine if a make/model is a verified off-road-oriented model (never inferred from SUV alone)."""
    if not model:
        return False
    canonical_make = resolve_manufacturer(make) if make else None
    cleaned_model = model.strip().lower()

    entries = (
        [MANUFACTURER_CATALOG[canonical_make]]
        if canonical_make and canonical_make in MANUFACTURER_CATALOG
        else list(MANUFACTURER_CATALOG.values())
    )
    for entry in entries:
        for model_name, model_entry in entry.models.items():
            if (
                model_name.lower() == cleaned_model
                or any(a.lower() == cleaned_model for a in model_entry.aliases)
            ) and model_entry.verified_off_road:
                return True
    return False


def expand_powertrain_group(group: PowertrainGroup | str) -> list[FuelType]:
    """Expand convenience powertrain groups into explicit FuelType values.

    Invariants:
    - EV = battery-electric (ELECTRIC) only. Never classify a hybrid as fully electric.
    - ICE = gasoline or diesel internal-combustion vehicles.
    - Hybrid = HEV (HYBRID).
    - PHEV = separately selectable plug-in hybrid (PLUGIN_HYBRID).
    """
    g = str(group).lower().strip()
    if g == PowertrainGroup.EV:
        return [FuelType.ELECTRIC]
    if g == PowertrainGroup.ICE:
        return [FuelType.GASOLINE, FuelType.DIESEL]
    if g == PowertrainGroup.HYBRID:
        return [FuelType.HYBRID]
    if g == PowertrainGroup.PHEV:
        return [FuelType.PLUGIN_HYBRID]
    if g in {PowertrainGroup.ALL, "any"}:
        return []
    return []


def derive_powertrain_from_fuel(fuel: FuelType) -> str:
    """Map a specific FuelType to its powertrain category."""
    if fuel == FuelType.ELECTRIC:
        return PowertrainGroup.EV.value
    if fuel in {FuelType.GASOLINE, FuelType.DIESEL, FuelType.LPG, FuelType.CNG}:
        return PowertrainGroup.ICE.value
    if fuel == FuelType.HYBRID:
        return PowertrainGroup.HYBRID.value
    if fuel == FuelType.PLUGIN_HYBRID:
        return PowertrainGroup.PHEV.value
    return "unknown"


class NormalizedListing(BaseModel):
    """Domain model representing a normalized vehicle listing from any source."""

    source: str = "myauto"
    source_listing_id: str
    url: str
    make: str | None = None
    model: str | None = None
    generation: str | None = None
    trim: str | None = None
    year: int | None = None
    fuel: FuelType = FuelType.UNKNOWN
    powertrain: str = "unknown"
    body_style: BodyStyle = BodyStyle.UNKNOWN
    drivetrain: Drivetrain = Drivetrain.UNKNOWN
    transmission: Transmission = Transmission.UNKNOWN
    engine: str | None = None
    mileage_km: int | None = None
    location: str | None = None
    customs_status: CustomsStatus = CustomsStatus.UNKNOWN
    price: float | None = None
    currency: str = "USD"
    usd_price: float | None = None
    description: str | None = None
    seller_type: str | None = None
    condition_indicators: dict[str, Any] = Field(default_factory=dict)
    photo_urls: list[str] = Field(default_factory=list)
    publication_date: datetime | None = None
    first_seen: datetime | None = None
    last_seen: datetime | None = None
