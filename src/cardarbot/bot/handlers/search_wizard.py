from __future__ import annotations

import logging
from enum import IntEnum
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from cardarbot.bot.auth import require_auth
from cardarbot.bot.callbacks import CB_CANCEL, CB_MAIN_MENU, CB_MENU_CREATE_SEARCH
from cardarbot.bot.handlers.core import (
    _ensure_user_and_settings,
    cancel_command,
    start_command,
)
from cardarbot.bot.keyboards import build_main_menu_keyboard
from cardarbot.database.repositories import SearchProfileRepository, UserRepository
from cardarbot.database.session import DatabaseManager
from cardarbot.domain.enums import (
    BodyStyle,
    CustomsFilterMode,
    Drivetrain,
    FuelType,
    OffRoadPreference,
    PowertrainGroup,
    ScanFrequency,
    Transmission,
)
from cardarbot.domain.search_profiles import SearchFilterConfig
from cardarbot.domain.vehicles import (
    MANUFACTURER_CATALOG,
    expand_powertrain_group,
    resolve_manufacturer,
    resolve_model,
    validate_make_model_combination,
)

logger = logging.getLogger("cardarbot.handlers.search_wizard")


class WizardStep(IntEnum):
    STEP_1_NAME = 1
    STEP_2_MANUFACTURER = 2
    STEP_3_MODEL = 3
    STEP_4_FUEL = 4
    STEP_5_BODY = 5
    STEP_6_DRIVETRAIN = 6
    STEP_7_OFFROAD = 7
    STEP_8_TRANSMISSION = 8
    STEP_9_BUDGET = 9
    STEP_10_YEAR = 10
    STEP_11_MILEAGE = 11
    STEP_12_LOCATION = 12
    STEP_13_CUSTOMS = 13
    STEP_14_MIN_PROFIT = 14
    STEP_15_DEAL_SCORE = 15
    STEP_16_FREQUENCY = 16
    STEP_17_CONFIRM = 17


WIZARD_MAKES = [
    "Toyota",
    "BMW",
    "Mercedes-Benz",
    "Honda",
    "Hyundai",
    "Kia",
    "Nissan",
    "Volkswagen",
    "Ford",
    "Subaru",
    "Lexus",
    "Mitsubishi",
    "Chevrolet",
    "Mazda",
    "Audi",
    "Porsche",
]


def _get_draft(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any]:
    if context.user_data is None:
        return {}
    if "wizard_draft" not in context.user_data:
        context.user_data["wizard_draft"] = {
            "edit_profile_id": None,
            "name": None,
            "auto_name": True,
            "makes": [],
            "models": [],
            "fuels": [],
            "body_styles": [],
            "drivetrains": [],
            "off_road_preference": OffRoadPreference.ANY.value,
            "transmissions": [],
            "min_price_usd": 500,
            "max_price_usd": 5000,
            "min_year": None,
            "max_year": None,
            "min_mileage_km": None,
            "max_mileage_km": None,
            "location": "Tbilisi",
            "customs_mode": CustomsFilterMode.CLEARED_ONLY.value,
            "min_profit_usd": 500,
            "min_deal_score": 70,
            "scan_frequency": ScanFrequency.DAILY.value,
        }
    return context.user_data["wizard_draft"]


def _build_filter_config_from_draft(draft: dict[str, Any]) -> SearchFilterConfig:
    return SearchFilterConfig(
        makes=list(draft.get("makes", [])),
        models=list(draft.get("models", [])),
        fuels=[FuelType(f) for f in draft.get("fuels", [])],
        body_styles=[BodyStyle(b) for b in draft.get("body_styles", [])],
        drivetrains=[Drivetrain(d) for d in draft.get("drivetrains", [])],
        off_road_preference=OffRoadPreference(draft.get("off_road_preference", "any")),
        transmissions=[Transmission(t) for t in draft.get("transmissions", [])],
        min_price_usd=int(draft.get("min_price_usd", 500)),
        max_price_usd=int(draft.get("max_price_usd", 5000)),
        min_year=draft.get("min_year"),
        max_year=draft.get("max_year"),
        min_mileage_km=draft.get("min_mileage_km"),
        max_mileage_km=draft.get("max_mileage_km"),
        location=draft.get("location", "Tbilisi"),
        customs_mode=CustomsFilterMode(draft.get("customs_mode", "cleared_only")),
        min_profit_usd=int(draft.get("min_profit_usd", 500)),
        min_deal_score=int(draft.get("min_deal_score", 70)),
        scan_frequency=ScanFrequency(draft.get("scan_frequency", "daily")),
    )


def _nav_row(back_step: int | None = None) -> list[InlineKeyboardButton]:
    row: list[InlineKeyboardButton] = []
    if back_step is not None:
        row.append(InlineKeyboardButton("⬅️ Back", callback_data=f"wiz:back:{back_step}"))
    row.append(InlineKeyboardButton("❌ Cancel", callback_data=CB_CANCEL))
    row.append(InlineKeyboardButton("🏠 Main Menu", callback_data=CB_MAIN_MENU))
    return row


async def _send_or_edit(
    update: Update,
    text: str,
    reply_markup: InlineKeyboardMarkup,
) -> None:
    if update.callback_query:
        await update.callback_query.edit_message_text(text=text, reply_markup=reply_markup)
    elif update.effective_message:
        await update.effective_message.reply_text(text=text, reply_markup=reply_markup)


# --- STEP RENDERERS ---


async def render_step_1_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_draft(context)
    current = draft.get("name") or "(Auto-generated)"
    text = (
        "🔎 **Step 1/17 — Search Name**\n\n"
        f"Current: `{current}`\n\n"
        "Type a custom name for your search (e.g., *Toyota Hybrid Deals*, *BMW Sedans*, "
        "*Electric Cars Under $5K*, *Cheap SUVs*), or tap **Auto-Generate Name** below:"
    )
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✨ Auto-Generate Name", callback_data="wiz:name:auto")],
            [
                InlineKeyboardButton(
                    "Toyota Hybrid Deals", callback_data="wiz:name:Toyota Hybrid Deals"
                ),
                InlineKeyboardButton(
                    "Electric Cars Under $5K", callback_data="wiz:name:Electric Cars Under $5K"
                ),
            ],
            _nav_row(None),
        ]
    )
    await _send_or_edit(update, text, kb)
    return WizardStep.STEP_1_NAME


async def render_step_2_manufacturer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_draft(context)
    selected: list[str] = draft.get("makes", [])
    sel_str = ", ".join(selected) if selected else "Any"
    text = (
        "🏭 **Step 2/17 — Manufacturer**\n\n"
        f"Selected: `{sel_str}`\n\n"
        "Tap one or more manufacturers to toggle selection, type a custom make name, "
        "or tap **Next ➡️** / **Any Manufacturer**:"
    )
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("🌐 Any Manufacturer", callback_data="wiz:make:ANY"),
            InlineKeyboardButton("➡️ Next (Confirm Make)", callback_data="wiz:make:NEXT"),
        ]
    ]
    for i in range(0, len(WIZARD_MAKES), 2):
        pair = WIZARD_MAKES[i : i + 2]
        btn_row = []
        for m in pair:
            prefix = "✅ " if m in selected else ""
            btn_row.append(InlineKeyboardButton(f"{prefix}{m}", callback_data=f"wiz:make:{m}"))
        rows.append(btn_row)
    rows.append([InlineKeyboardButton("➕ Other (Type in chat)", callback_data="wiz:make:OTHER")])
    rows.append(_nav_row(WizardStep.STEP_1_NAME))
    await _send_or_edit(update, text, InlineKeyboardMarkup(rows))
    return WizardStep.STEP_2_MANUFACTURER


async def render_step_3_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_draft(context)
    makes: list[str] = draft.get("makes", [])
    selected_models: list[str] = draft.get("models", [])
    sel_str = ", ".join(selected_models) if selected_models else "Any Model"

    available_models: list[str] = []
    for mk in makes:
        entry = MANUFACTURER_CATALOG.get(mk)
        if entry:
            for mod_name in entry.models:
                if mod_name not in available_models:
                    available_models.append(mod_name)

    text = (
        "🚘 **Step 3/17 — Model**\n\n"
        f"Selected Make(s): `{', '.join(makes) if makes else 'Any'}`\n"
        f"Selected Model(s): `{sel_str}`\n\n"
        "Select one or more models, type a model name/alias, or tap **Any Model**:"
    )
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("🌐 Any Model", callback_data="wiz:model:ANY"),
            InlineKeyboardButton("➡️ Next (Confirm Model)", callback_data="wiz:model:NEXT"),
        ]
    ]
    for i in range(0, len(available_models[:16]), 2):
        pair = available_models[i : i + 2]
        btn_row = []
        for mod in pair:
            prefix = "✅ " if mod in selected_models else ""
            btn_row.append(InlineKeyboardButton(f"{prefix}{mod}", callback_data=f"wiz:model:{mod}"))
        rows.append(btn_row)
    rows.append(_nav_row(WizardStep.STEP_2_MANUFACTURER))
    await _send_or_edit(update, text, InlineKeyboardMarkup(rows))
    return WizardStep.STEP_3_MODEL


async def render_step_4_fuel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_draft(context)
    fuels: list[str] = draft.get("fuels", [])
    sel_str = ", ".join(fuels) if fuels else "Any"
    text = (
        "⛽ **Step 4/17 — Fuel & Powertrain**\n\n"
        f"Selected: `{sel_str}`\n\n"
        "Choose individual fuel types or convenience powertrain groups "
        "(Note: EV = battery-electric BEV only; Hybrid = HEV; PHEV = plug-in hybrid):"
    )
    fuel_options = [
        ("Gasoline", FuelType.GASOLINE.value),
        ("Diesel", FuelType.DIESEL.value),
        ("Hybrid (HEV)", FuelType.HYBRID.value),
        ("Plug-in Hybrid (PHEV)", FuelType.PLUGIN_HYBRID.value),
        ("Electric (BEV)", FuelType.ELECTRIC.value),
        ("LPG", FuelType.LPG.value),
        ("CNG", FuelType.CNG.value),
        ("Other", FuelType.OTHER.value),
    ]
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("🌐 Any / All", callback_data="wiz:fuel:ANY"),
            InlineKeyboardButton("➡️ Next", callback_data="wiz:fuel:NEXT"),
        ],
        [
            InlineKeyboardButton("⚡ Group: EV (BEV)", callback_data="wiz:fuelgrp:ev"),
            InlineKeyboardButton("🔥 Group: ICE", callback_data="wiz:fuelgrp:ice"),
            InlineKeyboardButton("🔋 Group: Hybrid", callback_data="wiz:fuelgrp:hybrid"),
        ],
    ]
    for i in range(0, len(fuel_options), 2):
        pair = fuel_options[i : i + 2]
        btn_row = []
        for label, val in pair:
            prefix = "✅ " if val in fuels else ""
            btn_row.append(
                InlineKeyboardButton(f"{prefix}{label}", callback_data=f"wiz:fuel:{val}")
            )
        rows.append(btn_row)
    rows.append(_nav_row(WizardStep.STEP_3_MODEL))
    await _send_or_edit(update, text, InlineKeyboardMarkup(rows))
    return WizardStep.STEP_4_FUEL


async def render_step_5_body(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_draft(context)
    bodies: list[str] = draft.get("body_styles", [])
    sel_str = ", ".join(bodies) if bodies else "Any"
    text = (
        "🚙 **Step 5/17 — Body Style**\n\n"
        f"Selected: `{sel_str}`\n\n"
        "Select one or more body styles (Off-road capability is configured separately in Step 7):"
    )
    body_options = [
        ("Sedan", BodyStyle.SEDAN.value),
        ("Coupe", BodyStyle.COUPE.value),
        ("Hatchback", BodyStyle.HATCHBACK.value),
        ("Wagon", BodyStyle.WAGON.value),
        ("SUV / Crossover", BodyStyle.SUV_CROSSOVER.value),
        ("Pickup", BodyStyle.PICKUP.value),
        ("Convertible", BodyStyle.CONVERTIBLE.value),
        ("Minivan", BodyStyle.MINIVAN.value),
        ("Van", BodyStyle.VAN.value),
        ("Other", BodyStyle.OTHER.value),
    ]
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("🌐 Any Body Style", callback_data="wiz:body:ANY"),
            InlineKeyboardButton("➡️ Next", callback_data="wiz:body:NEXT"),
        ]
    ]
    for i in range(0, len(body_options), 2):
        pair = body_options[i : i + 2]
        btn_row = []
        for label, val in pair:
            prefix = "✅ " if val in bodies else ""
            btn_row.append(
                InlineKeyboardButton(f"{prefix}{label}", callback_data=f"wiz:body:{val}")
            )
        rows.append(btn_row)
    rows.append(_nav_row(WizardStep.STEP_4_FUEL))
    await _send_or_edit(update, text, InlineKeyboardMarkup(rows))
    return WizardStep.STEP_5_BODY


async def render_step_6_drivetrain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_draft(context)
    drives: list[str] = draft.get("drivetrains", [])
    sel_str = ", ".join(d.upper() for d in drives) if drives else "Any"
    text = f"⚙️ **Step 6/17 — Drivetrain**\n\nSelected: `{sel_str}`\n\nChoose drivetrain filter:"
    drive_options = [
        ("FWD", Drivetrain.FWD.value),
        ("RWD", Drivetrain.RWD.value),
        ("AWD", Drivetrain.AWD.value),
        ("4WD", Drivetrain.FOUR_WD.value),
    ]
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("🌐 Any Drivetrain", callback_data="wiz:drive:ANY"),
            InlineKeyboardButton("➡️ Next", callback_data="wiz:drive:NEXT"),
        ],
        [
            InlineKeyboardButton("🏔️ Both AWD & 4WD", callback_data="wiz:drive:AWD_4WD"),
        ],
    ]
    btn_row = []
    for label, val in drive_options:
        prefix = "✅ " if val in drives else ""
        btn_row.append(InlineKeyboardButton(f"{prefix}{label}", callback_data=f"wiz:drive:{val}"))
    rows.append(btn_row)
    rows.append(_nav_row(WizardStep.STEP_5_BODY))
    await _send_or_edit(update, text, InlineKeyboardMarkup(rows))
    return WizardStep.STEP_6_DRIVETRAIN


async def render_step_7_offroad(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_draft(context)
    current = draft.get("off_road_preference", OffRoadPreference.ANY.value)
    text = (
        "🏔️ **Step 7/17 — Off-Road Preferences**\n\n"
        f"Current: `{current}`\n\n"
        "Select off-road capability preference (Genuine off-road capability is never inferred from SUV body style alone):"
    )
    rows = [
        [
            InlineKeyboardButton(
                "Any (No off-road requirement)",
                callback_data=f"wiz:offroad:{OffRoadPreference.ANY.value}",
            )
        ],
        [
            InlineKeyboardButton(
                "AWD/4WD Preferred",
                callback_data=f"wiz:offroad:{OffRoadPreference.AWD_4WD_PREFERRED.value}",
            )
        ],
        [
            InlineKeyboardButton(
                "AWD/4WD Required",
                callback_data=f"wiz:offroad:{OffRoadPreference.AWD_4WD_REQUIRED.value}",
            )
        ],
        [
            InlineKeyboardButton(
                "Verified Off-Road-Oriented Model Only",
                callback_data=f"wiz:offroad:{OffRoadPreference.VERIFIED_OFF_ROAD_MODEL.value}",
            )
        ],
        _nav_row(WizardStep.STEP_6_DRIVETRAIN),
    ]
    await _send_or_edit(update, text, InlineKeyboardMarkup(rows))
    return WizardStep.STEP_7_OFFROAD


async def render_step_8_transmission(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_draft(context)
    trans: list[str] = draft.get("transmissions", [])
    sel_str = ", ".join(trans) if trans else "Any"
    text = (
        "🕹️ **Step 8/17 — Transmission**\n\n"
        f"Selected: `{sel_str}`\n\n"
        "Select allowed transmission types:"
    )
    opts = [
        ("Automatic", Transmission.AUTOMATIC.value),
        ("Manual", Transmission.MANUAL.value),
        ("CVT", Transmission.CVT.value),
        ("Other", Transmission.OTHER.value),
    ]
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("🌐 Any Transmission", callback_data="wiz:trans:ANY"),
            InlineKeyboardButton("➡️ Next", callback_data="wiz:trans:NEXT"),
        ]
    ]
    btn_row = []
    for label, val in opts:
        prefix = "✅ " if val in trans else ""
        btn_row.append(InlineKeyboardButton(f"{prefix}{label}", callback_data=f"wiz:trans:{val}"))
    rows.append(btn_row)
    rows.append(_nav_row(WizardStep.STEP_7_OFFROAD))
    await _send_or_edit(update, text, InlineKeyboardMarkup(rows))
    return WizardStep.STEP_8_TRANSMISSION


async def render_step_9_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_draft(context)
    min_p = draft.get("min_price_usd", 500)
    max_p = draft.get("max_price_usd", 5000)
    text = (
        "💰 **Step 9/17 — Budget (USD)**\n\n"
        f"Current Range: `${min_p:,} – ${max_p:,}`\n\n"
        "Select a preset budget range or type a custom range in chat (e.g. `500-5000` or `1000 4500`):"
    )
    rows = [
        [
            InlineKeyboardButton("$500 – $5,000 (Default)", callback_data="wiz:budget:500_5000"),
            InlineKeyboardButton("$500 – $3,500", callback_data="wiz:budget:500_3500"),
        ],
        [
            InlineKeyboardButton("$1,500 – $6,500", callback_data="wiz:budget:1500_6500"),
            InlineKeyboardButton("$2,000 – $10,000", callback_data="wiz:budget:2000_10000"),
        ],
        [InlineKeyboardButton("➡️ Keep Current Budget", callback_data="wiz:budget:KEEP")],
        _nav_row(WizardStep.STEP_8_TRANSMISSION),
    ]
    await _send_or_edit(update, text, InlineKeyboardMarkup(rows))
    return WizardStep.STEP_9_BUDGET


async def render_step_10_year(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_draft(context)
    min_y = draft.get("min_year")
    max_y = draft.get("max_year")
    yr_str = f"{min_y or 'Any'} – {max_y or 'Any'}"
    text = (
        "📅 **Step 10/17 — Model Year**\n\n"
        f"Current: `{yr_str}`\n\n"
        "Select a year range or type a custom range in chat (e.g. `2010-2017` or `2012+`):"
    )
    rows = [
        [
            InlineKeyboardButton("🌐 Any Year", callback_data="wiz:year:ANY"),
            InlineKeyboardButton("2008 – 2016", callback_data="wiz:year:2008_2016"),
        ],
        [
            InlineKeyboardButton("2010 – 2017", callback_data="wiz:year:2010_2017"),
            InlineKeyboardButton("2012 – 2020", callback_data="wiz:year:2012_2020"),
        ],
        [
            InlineKeyboardButton("2015+", callback_data="wiz:year:2015_None"),
        ],
        _nav_row(WizardStep.STEP_9_BUDGET),
    ]
    await _send_or_edit(update, text, InlineKeyboardMarkup(rows))
    return WizardStep.STEP_10_YEAR


async def render_step_11_mileage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_draft(context)
    min_m = draft.get("min_mileage_km")
    max_m = draft.get("max_mileage_km")
    m_str = f"{min_m or 0:,} – {max_m:,} km" if max_m else "Any"
    text = (
        "🛣️ **Step 11/17 — Mileage (Normalized to km)**\n\n"
        f"Current: `{m_str}`\n\n"
        "Choose a maximum mileage or type a custom range in chat (e.g. `200000` or `50000-180000` or `120000 mi`):"
    )
    rows = [
        [
            InlineKeyboardButton("🌐 Any Mileage", callback_data="wiz:mileage:ANY"),
            InlineKeyboardButton("Under 150,000 km", callback_data="wiz:mileage:0_150000"),
        ],
        [
            InlineKeyboardButton("Under 200,000 km", callback_data="wiz:mileage:0_200000"),
            InlineKeyboardButton("Under 250,000 km", callback_data="wiz:mileage:0_250000"),
        ],
        _nav_row(WizardStep.STEP_10_YEAR),
    ]
    await _send_or_edit(update, text, InlineKeyboardMarkup(rows))
    return WizardStep.STEP_11_MILEAGE


async def render_step_12_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (
        "📍 **Step 12/17 — Location**\n\n"
        "Default: **Tbilisi, Georgia**\n"
        "(Only Tbilisi is supported initially; architecture supports future Georgian cities.)"
    )
    rows = [
        [InlineKeyboardButton("📍 Tbilisi, Georgia (Default)", callback_data="wiz:loc:Tbilisi")],
        _nav_row(WizardStep.STEP_11_MILEAGE),
    ]
    await _send_or_edit(update, text, InlineKeyboardMarkup(rows))
    return WizardStep.STEP_12_LOCATION


async def render_step_13_customs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (
        "🛃 **Step 13/17 — Customs Status**\n\n"
        "Default: **Customs-cleared only** (განბაჟებული)\n"
        "Note: Unknown customs status is never treated as confirmed cleared."
    )
    rows = [
        [
            InlineKeyboardButton(
                "✅ Customs-Cleared Only (Default)",
                callback_data=f"wiz:customs:{CustomsFilterMode.CLEARED_ONLY.value}",
            )
        ],
        [
            InlineKeyboardButton(
                "🚢 Include Uncleared",
                callback_data=f"wiz:customs:{CustomsFilterMode.INCLUDE_UNCLEARED.value}",
            )
        ],
        [
            InlineKeyboardButton(
                "🌐 Any Status",
                callback_data=f"wiz:customs:{CustomsFilterMode.ANY.value}",
            )
        ],
        _nav_row(WizardStep.STEP_12_LOCATION),
    ]
    await _send_or_edit(update, text, InlineKeyboardMarkup(rows))
    return WizardStep.STEP_13_CUSTOMS


async def render_step_14_min_profit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (
        "💵 **Step 14/17 — Minimum Expected Net Profit (USD)**\n\n"
        "Select a preset minimum profit or type a custom USD amount in chat:"
    )
    rows = [
        [
            InlineKeyboardButton("$300", callback_data="wiz:profit:300"),
            InlineKeyboardButton("$500 (Default)", callback_data="wiz:profit:500"),
        ],
        [
            InlineKeyboardButton("$750", callback_data="wiz:profit:750"),
            InlineKeyboardButton("$1,000", callback_data="wiz:profit:1000"),
        ],
        _nav_row(WizardStep.STEP_13_CUSTOMS),
    ]
    await _send_or_edit(update, text, InlineKeyboardMarkup(rows))
    return WizardStep.STEP_14_MIN_PROFIT


async def render_step_15_deal_score(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (
        "⭐ **Step 15/17 — Deal Score Threshold (0–100)**\n\n"
        "Default: **70/100** (Strong & Exceptional deals)\n"
        "Select a threshold or type a number (0–100) in chat:"
    )
    rows = [
        [
            InlineKeyboardButton("55/100 (Review+)", callback_data="wiz:score:55"),
            InlineKeyboardButton("70/100 (Default - Strong+)", callback_data="wiz:score:70"),
        ],
        [
            InlineKeyboardButton("80/100 (High Strong+)", callback_data="wiz:score:80"),
            InlineKeyboardButton("85/100 (Exceptional Only)", callback_data="wiz:score:85"),
        ],
        _nav_row(WizardStep.STEP_14_MIN_PROFIT),
    ]
    await _send_or_edit(update, text, InlineKeyboardMarkup(rows))
    return WizardStep.STEP_15_DEAL_SCORE


async def render_step_16_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (
        "⏰ **Step 16/17 — Scan Frequency**\n\n"
        "Default: **Daily**\n"
        "Choose how often CarDarBot should automatically scan for this profile:"
    )
    rows = [
        [
            InlineKeyboardButton(
                "📅 Daily (Default)", callback_data=f"wiz:freq:{ScanFrequency.DAILY.value}"
            )
        ],
        [
            InlineKeyboardButton(
                "🕛 Every 12 hours", callback_data=f"wiz:freq:{ScanFrequency.EVERY_12_HOURS.value}"
            )
        ],
        [
            InlineKeyboardButton(
                "🕕 Every 6 hours", callback_data=f"wiz:freq:{ScanFrequency.EVERY_6_HOURS.value}"
            )
        ],
        [
            InlineKeyboardButton(
                "🖐️ Manual only", callback_data=f"wiz:freq:{ScanFrequency.MANUAL_ONLY.value}"
            )
        ],
        _nav_row(WizardStep.STEP_15_DEAL_SCORE),
    ]
    await _send_or_edit(update, text, InlineKeyboardMarkup(rows))
    return WizardStep.STEP_16_FREQUENCY


async def render_step_17_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_draft(context)
    cfg = _build_filter_config_from_draft(draft)
    if draft.get("auto_name") or not draft.get("name"):
        draft["name"] = cfg.generate_auto_name()
    summary = cfg.format_summary(draft["name"])

    text = f"📋 **Step 17/17 — Confirm Search Profile**\n\n{summary}"
    rows = [
        [
            InlineKeyboardButton("✅ Save and Activate", callback_data="wiz:confirm:SAVE"),
        ],
        [
            InlineKeyboardButton("✏️ Edit (Restart Wizard)", callback_data="wiz:confirm:EDIT"),
            InlineKeyboardButton("❌ Cancel", callback_data=CB_CANCEL),
        ],
    ]
    await _send_or_edit(update, text, InlineKeyboardMarkup(rows))
    return WizardStep.STEP_17_CONFIRM


STEP_RENDERERS = {
    WizardStep.STEP_1_NAME: render_step_1_name,
    WizardStep.STEP_2_MANUFACTURER: render_step_2_manufacturer,
    WizardStep.STEP_3_MODEL: render_step_3_model,
    WizardStep.STEP_4_FUEL: render_step_4_fuel,
    WizardStep.STEP_5_BODY: render_step_5_body,
    WizardStep.STEP_6_DRIVETRAIN: render_step_6_drivetrain,
    WizardStep.STEP_7_OFFROAD: render_step_7_offroad,
    WizardStep.STEP_8_TRANSMISSION: render_step_8_transmission,
    WizardStep.STEP_9_BUDGET: render_step_9_budget,
    WizardStep.STEP_10_YEAR: render_step_10_year,
    WizardStep.STEP_11_MILEAGE: render_step_11_mileage,
    WizardStep.STEP_12_LOCATION: render_step_12_location,
    WizardStep.STEP_13_CUSTOMS: render_step_13_customs,
    WizardStep.STEP_14_MIN_PROFIT: render_step_14_min_profit,
    WizardStep.STEP_15_DEAL_SCORE: render_step_15_deal_score,
    WizardStep.STEP_16_FREQUENCY: render_step_16_frequency,
    WizardStep.STEP_17_CONFIRM: render_step_17_confirm,
}


# --- ENTRY & STEP HANDLERS ---


@require_auth
async def newsearch_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the 17-step Search Creation Wizard from /newsearch or 🔎 Create Search button."""
    user_id, _ = _ensure_user_and_settings(update, context)
    db: DatabaseManager = context.application.bot_data["db"]
    with db.session() as session:
        repo = UserRepository(session)
        user = repo.get_by_telegram_id(update.effective_user.id)  # type: ignore[union-attr]
        max_price = user.settings.default_max_price_usd if user and user.settings else 5000
        min_profit = user.settings.default_min_profit_usd if user and user.settings else 500
        min_score = user.settings.default_min_score if user and user.settings else 70
        city = user.settings.default_city if user and user.settings else "Tbilisi"

    if context.user_data is not None:
        context.user_data.pop("wizard_draft", None)
    draft = _get_draft(context)
    draft["max_price_usd"] = max_price
    draft["min_profit_usd"] = min_profit
    draft["min_deal_score"] = min_score
    draft["location"] = city

    if update.callback_query:
        await update.callback_query.answer()
    return await render_step_1_name(update, context)


@require_auth
async def handle_wizard_back_or_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.data is None:
        return ConversationHandler.END
    data = query.data
    if data in {CB_CANCEL, CB_MAIN_MENU}:
        return await cancel_command(update, context)
    if data.startswith("wiz:back:"):
        target_step = int(data.split(":")[2])
        await query.answer()
        renderer = STEP_RENDERERS.get(WizardStep(target_step), render_step_1_name)
        return await renderer(update, context)
    return ConversationHandler.END


@require_auth
async def step_1_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_draft(context)
    if update.callback_query and update.callback_query.data:
        await update.callback_query.answer()
        val = update.callback_query.data.split(":", 2)[2]
        if val == "auto":
            draft["auto_name"] = True
            draft["name"] = None
        else:
            draft["auto_name"] = False
            draft["name"] = val
        return await render_step_2_manufacturer(update, context)

    if update.effective_message and update.effective_message.text:
        custom_name = update.effective_message.text.strip()[:100]
        draft["auto_name"] = False
        draft["name"] = custom_name
        return await render_step_2_manufacturer(update, context)
    return WizardStep.STEP_1_NAME


@require_auth
async def step_2_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_draft(context)
    makes: list[str] = draft["makes"]
    if update.callback_query and update.callback_query.data:
        val = update.callback_query.data.split(":", 2)[2]
        await update.callback_query.answer()
        if val == "ANY":
            draft["makes"] = []
            draft["models"] = []
            return await render_step_3_model(update, context)
        if val == "NEXT":
            return await render_step_3_model(update, context)
        if val == "OTHER":
            await update.callback_query.edit_message_text(
                "🏭 Please type the manufacturer name in chat (e.g., `Jeep`, `Land Rover`, `Volvo`):"
            )
            return WizardStep.STEP_2_MANUFACTURER
        if val in makes:
            makes.remove(val)
        else:
            makes.append(val)
        return await render_step_2_manufacturer(update, context)

    if update.effective_message and update.effective_message.text:
        resolved = resolve_manufacturer(update.effective_message.text.strip())
        if resolved and resolved not in makes:
            makes.append(resolved)
        return await render_step_3_model(update, context)
    return WizardStep.STEP_2_MANUFACTURER


@require_auth
async def step_3_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_draft(context)
    makes: list[str] = draft["makes"]
    models: list[str] = draft["models"]
    if update.callback_query and update.callback_query.data:
        val = update.callback_query.data.split(":", 2)[2]
        await update.callback_query.answer()
        if val == "ANY":
            draft["models"] = []
            return await render_step_4_fuel(update, context)
        if val == "NEXT":
            return await render_step_4_fuel(update, context)
        if val in models:
            models.remove(val)
        else:
            models.append(val)
        return await render_step_3_model(update, context)

    if update.effective_message and update.effective_message.text:
        raw_mod = update.effective_message.text.strip()
        primary_make = makes[0] if len(makes) == 1 else None
        if primary_make and not validate_make_model_combination(primary_make, raw_mod):
            await update.effective_message.reply_text(
                f"⚠️ Model `{raw_mod}` does not match manufacturer `{primary_make}` in the catalog. "
                "Please choose a valid model or tap **Any Model**."
            )
            return await render_step_3_model(update, context)
        resolved = resolve_model(primary_make, raw_mod)
        if resolved and resolved not in models:
            models.append(resolved)
        return await render_step_4_fuel(update, context)
    return WizardStep.STEP_3_MODEL


@require_auth
async def step_4_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_draft(context)
    fuels: list[str] = draft["fuels"]
    if update.callback_query and update.callback_query.data:
        data = update.callback_query.data
        await update.callback_query.answer()
        if data.startswith("wiz:fuelgrp:"):
            grp = data.split(":", 2)[2]
            expanded = [f.value for f in expand_powertrain_group(PowertrainGroup(grp))]
            for f_val in expanded:
                if f_val not in fuels:
                    fuels.append(f_val)
            return await render_step_4_fuel(update, context)

        val = data.split(":", 2)[2]
        if val == "ANY":
            draft["fuels"] = []
            return await render_step_5_body(update, context)
        if val == "NEXT":
            return await render_step_5_body(update, context)
        if val in fuels:
            fuels.remove(val)
        else:
            fuels.append(val)
        return await render_step_4_fuel(update, context)
    return WizardStep.STEP_4_FUEL


@require_auth
async def step_5_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_draft(context)
    bodies: list[str] = draft["body_styles"]
    if update.callback_query and update.callback_query.data:
        val = update.callback_query.data.split(":", 2)[2]
        await update.callback_query.answer()
        if val == "ANY":
            draft["body_styles"] = []
            return await render_step_6_drivetrain(update, context)
        if val == "NEXT":
            return await render_step_6_drivetrain(update, context)
        if val in bodies:
            bodies.remove(val)
        else:
            bodies.append(val)
        return await render_step_5_body(update, context)
    return WizardStep.STEP_5_BODY


@require_auth
async def step_6_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_draft(context)
    drives: list[str] = draft["drivetrains"]
    if update.callback_query and update.callback_query.data:
        val = update.callback_query.data.split(":", 2)[2]
        await update.callback_query.answer()
        if val == "ANY":
            draft["drivetrains"] = []
            return await render_step_7_offroad(update, context)
        if val == "NEXT":
            return await render_step_7_offroad(update, context)
        if val == "AWD_4WD":
            draft["drivetrains"] = [Drivetrain.AWD.value, Drivetrain.FOUR_WD.value]
            return await render_step_7_offroad(update, context)
        if val in drives:
            drives.remove(val)
        else:
            drives.append(val)
        return await render_step_6_drivetrain(update, context)
    return WizardStep.STEP_6_DRIVETRAIN


@require_auth
async def step_7_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_draft(context)
    if update.callback_query and update.callback_query.data:
        val = update.callback_query.data.split(":", 2)[2]
        await update.callback_query.answer()
        draft["off_road_preference"] = val
        return await render_step_8_transmission(update, context)
    return WizardStep.STEP_7_OFFROAD


@require_auth
async def step_8_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_draft(context)
    trans: list[str] = draft["transmissions"]
    if update.callback_query and update.callback_query.data:
        val = update.callback_query.data.split(":", 2)[2]
        await update.callback_query.answer()
        if val == "ANY":
            draft["transmissions"] = []
            return await render_step_9_budget(update, context)
        if val == "NEXT":
            return await render_step_9_budget(update, context)
        if val in trans:
            trans.remove(val)
        else:
            trans.append(val)
        return await render_step_8_transmission(update, context)
    return WizardStep.STEP_8_TRANSMISSION


@require_auth
async def step_9_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_draft(context)
    if update.callback_query and update.callback_query.data:
        val = update.callback_query.data.split(":", 2)[2]
        await update.callback_query.answer()
        if val != "KEEP":
            min_s, max_s = val.split("_")
            draft["min_price_usd"] = int(min_s)
            draft["max_price_usd"] = int(max_s)
        return await render_step_10_year(update, context)

    if update.effective_message and update.effective_message.text:
        import re

        nums = [
            int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", update.effective_message.text)
        ]
        if len(nums) == 1:
            draft["min_price_usd"] = 500 if nums[0] >= 500 else 0
            draft["max_price_usd"] = nums[0]
        elif len(nums) >= 2:
            if nums[0] > nums[1]:
                await update.effective_message.reply_text(
                    "⚠️ Minimum price cannot exceed maximum price. Please enter a valid range (e.g. `500-5000`)."
                )
                return WizardStep.STEP_9_BUDGET
            draft["min_price_usd"] = nums[0]
            draft["max_price_usd"] = nums[1]
        else:
            await update.effective_message.reply_text("⚠️ Please enter valid numbers for budget.")
            return WizardStep.STEP_9_BUDGET
        return await render_step_10_year(update, context)
    return WizardStep.STEP_9_BUDGET


@require_auth
async def step_10_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_draft(context)
    if update.callback_query and update.callback_query.data:
        val = update.callback_query.data.split(":", 2)[2]
        await update.callback_query.answer()
        if val == "ANY":
            draft["min_year"] = None
            draft["max_year"] = None
        else:
            y1, y2 = val.split("_")
            draft["min_year"] = None if y1 == "None" else int(y1)
            draft["max_year"] = None if y2 == "None" else int(y2)
        return await render_step_11_mileage(update, context)

    if update.effective_message and update.effective_message.text:
        import re

        years = [
            int(y) for y in re.findall(r"\b(19[5-9]\d|20[0-3]\d)\b", update.effective_message.text)
        ]
        if len(years) == 1:
            draft["min_year"] = years[0]
            draft["max_year"] = None
        elif len(years) >= 2:
            if years[0] > years[1]:
                await update.effective_message.reply_text(
                    "⚠️ Minimum year cannot exceed maximum year."
                )
                return WizardStep.STEP_10_YEAR
            draft["min_year"] = years[0]
            draft["max_year"] = years[1]
        else:
            await update.effective_message.reply_text(
                "⚠️ Please enter valid 4-digit years (e.g. `2010-2017`)."
            )
            return WizardStep.STEP_10_YEAR
        return await render_step_11_mileage(update, context)
    return WizardStep.STEP_10_YEAR


@require_auth
async def step_11_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_draft(context)
    if update.callback_query and update.callback_query.data:
        val = update.callback_query.data.split(":", 2)[2]
        await update.callback_query.answer()
        if val == "ANY":
            draft["min_mileage_km"] = None
            draft["max_mileage_km"] = None
        else:
            m1, m2 = val.split("_")
            draft["min_mileage_km"] = int(m1) if int(m1) > 0 else None
            draft["max_mileage_km"] = int(m2)
        return await render_step_12_location(update, context)

    if update.effective_message and update.effective_message.text:
        import re

        raw = update.effective_message.text.lower()
        is_miles = "mi" in raw or "მილი" in raw
        nums = [int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", raw)]
        factor = 1.60934 if is_miles else 1.0
        if len(nums) == 1:
            draft["min_mileage_km"] = None
            draft["max_mileage_km"] = int(round(nums[0] * factor))
        elif len(nums) >= 2:
            if nums[0] > nums[1]:
                await update.effective_message.reply_text(
                    "⚠️ Minimum mileage cannot exceed maximum mileage."
                )
                return WizardStep.STEP_11_MILEAGE
            draft["min_mileage_km"] = int(round(nums[0] * factor))
            draft["max_mileage_km"] = int(round(nums[1] * factor))
        else:
            await update.effective_message.reply_text("⚠️ Please enter a valid mileage number.")
            return WizardStep.STEP_11_MILEAGE
        return await render_step_12_location(update, context)
    return WizardStep.STEP_11_MILEAGE


@require_auth
async def step_12_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_draft(context)
    if update.callback_query and update.callback_query.data:
        await update.callback_query.answer()
        draft["location"] = "Tbilisi"
        return await render_step_13_customs(update, context)
    return WizardStep.STEP_12_LOCATION


@require_auth
async def step_13_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_draft(context)
    if update.callback_query and update.callback_query.data:
        val = update.callback_query.data.split(":", 2)[2]
        await update.callback_query.answer()
        draft["customs_mode"] = val
        return await render_step_14_min_profit(update, context)
    return WizardStep.STEP_13_CUSTOMS


@require_auth
async def step_14_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_draft(context)
    if update.callback_query and update.callback_query.data:
        val = update.callback_query.data.split(":", 2)[2]
        await update.callback_query.answer()
        draft["min_profit_usd"] = int(val)
        return await render_step_15_deal_score(update, context)

    if update.effective_message and update.effective_message.text:
        import re

        nums = [
            int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", update.effective_message.text)
        ]
        if nums:
            draft["min_profit_usd"] = nums[0]
            return await render_step_15_deal_score(update, context)
        await update.effective_message.reply_text("⚠️ Please enter a valid profit amount in USD.")
    return WizardStep.STEP_14_MIN_PROFIT


@require_auth
async def step_15_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_draft(context)
    if update.callback_query and update.callback_query.data:
        val = update.callback_query.data.split(":", 2)[2]
        await update.callback_query.answer()
        draft["min_deal_score"] = int(val)
        return await render_step_16_frequency(update, context)

    if update.effective_message and update.effective_message.text:
        import re

        nums = [int(n) for n in re.findall(r"\d+", update.effective_message.text)]
        if nums and 0 <= nums[0] <= 100:
            draft["min_deal_score"] = nums[0]
            return await render_step_16_frequency(update, context)
        await update.effective_message.reply_text("⚠️ Please enter a score between 0 and 100.")
    return WizardStep.STEP_15_DEAL_SCORE


@require_auth
async def step_16_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_draft(context)
    if update.callback_query and update.callback_query.data:
        val = update.callback_query.data.split(":", 2)[2]
        await update.callback_query.answer()
        draft["scan_frequency"] = val
        return await render_step_17_confirm(update, context)
    return WizardStep.STEP_16_FREQUENCY


@require_auth
async def step_17_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Persist search profile ONLY when user confirms Save and Activate."""
    draft = _get_draft(context)
    query = update.callback_query
    if query is None or query.data is None:
        return WizardStep.STEP_17_CONFIRM

    action = query.data.split(":", 2)[2]
    if action == "EDIT":
        await query.answer("Restarting wizard to edit settings")
        return await render_step_1_name(update, context)

    if action == "SAVE":
        user_id, _ = _ensure_user_and_settings(update, context)
        db: DatabaseManager = context.application.bot_data["db"]
        cfg = _build_filter_config_from_draft(draft)
        name = draft.get("name") or cfg.generate_auto_name()
        edit_id = draft.get("edit_profile_id")

        with db.session() as session:
            repo = SearchProfileRepository(session)
            if edit_id is not None:
                saved = repo.update_profile(
                    profile_id=int(edit_id),
                    user_id=user_id,
                    name=name,
                    filters=cfg,
                    is_active=True,
                )
            else:
                saved = repo.create_profile(
                    user_id=user_id,
                    name=name,
                    filters=cfg,
                    is_active=True,
                )

        if context.user_data is not None:
            context.user_data.pop("wizard_draft", None)

        await query.answer("✅ Search profile saved and activated!")
        profile_id_str = f"#{saved.id}" if saved and saved.id else ""
        await query.edit_message_text(
            f"✅ **Search Profile Saved & Activated!** ({profile_id_str})\n\n"
            f"{cfg.format_summary(name)}\n\n"
            "Use /searches to manage or run this search anytime.",
            reply_markup=build_main_menu_keyboard(),
        )
        return ConversationHandler.END

    return WizardStep.STEP_17_CONFIRM


def build_search_wizard_conversation_handler() -> ConversationHandler[Any]:
    """Construct the python-telegram-bot ConversationHandler for the 17-step search wizard."""
    back_cancel_filter = CallbackQueryHandler(
        handle_wizard_back_or_cancel,
        pattern=f"^(wiz:back:\\d+|{CB_CANCEL}|{CB_MAIN_MENU})$",
    )
    return ConversationHandler(
        entry_points=[
            CommandHandler("newsearch", newsearch_entry),
            CallbackQueryHandler(newsearch_entry, pattern=f"^{CB_MENU_CREATE_SEARCH}$"),
            CallbackQueryHandler(start_edit_profile_wizard, pattern=r"^srch:edit:\d+$"),
        ],
        states={
            WizardStep.STEP_1_NAME: [
                back_cancel_filter,
                CallbackQueryHandler(step_1_handler, pattern=r"^wiz:name:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, step_1_handler),
            ],
            WizardStep.STEP_2_MANUFACTURER: [
                back_cancel_filter,
                CallbackQueryHandler(step_2_handler, pattern=r"^wiz:make:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, step_2_handler),
            ],
            WizardStep.STEP_3_MODEL: [
                back_cancel_filter,
                CallbackQueryHandler(step_3_handler, pattern=r"^wiz:model:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, step_3_handler),
            ],
            WizardStep.STEP_4_FUEL: [
                back_cancel_filter,
                CallbackQueryHandler(step_4_handler, pattern=r"^wiz:fuel(grp)?:"),
            ],
            WizardStep.STEP_5_BODY: [
                back_cancel_filter,
                CallbackQueryHandler(step_5_handler, pattern=r"^wiz:body:"),
            ],
            WizardStep.STEP_6_DRIVETRAIN: [
                back_cancel_filter,
                CallbackQueryHandler(step_6_handler, pattern=r"^wiz:drive:"),
            ],
            WizardStep.STEP_7_OFFROAD: [
                back_cancel_filter,
                CallbackQueryHandler(step_7_handler, pattern=r"^wiz:offroad:"),
            ],
            WizardStep.STEP_8_TRANSMISSION: [
                back_cancel_filter,
                CallbackQueryHandler(step_8_handler, pattern=r"^wiz:trans:"),
            ],
            WizardStep.STEP_9_BUDGET: [
                back_cancel_filter,
                CallbackQueryHandler(step_9_handler, pattern=r"^wiz:budget:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, step_9_handler),
            ],
            WizardStep.STEP_10_YEAR: [
                back_cancel_filter,
                CallbackQueryHandler(step_10_handler, pattern=r"^wiz:year:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, step_10_handler),
            ],
            WizardStep.STEP_11_MILEAGE: [
                back_cancel_filter,
                CallbackQueryHandler(step_11_handler, pattern=r"^wiz:mileage:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, step_11_handler),
            ],
            WizardStep.STEP_12_LOCATION: [
                back_cancel_filter,
                CallbackQueryHandler(step_12_handler, pattern=r"^wiz:loc:"),
            ],
            WizardStep.STEP_13_CUSTOMS: [
                back_cancel_filter,
                CallbackQueryHandler(step_13_handler, pattern=r"^wiz:customs:"),
            ],
            WizardStep.STEP_14_MIN_PROFIT: [
                back_cancel_filter,
                CallbackQueryHandler(step_14_handler, pattern=r"^wiz:profit:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, step_14_handler),
            ],
            WizardStep.STEP_15_DEAL_SCORE: [
                back_cancel_filter,
                CallbackQueryHandler(step_15_handler, pattern=r"^wiz:score:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, step_15_handler),
            ],
            WizardStep.STEP_16_FREQUENCY: [
                back_cancel_filter,
                CallbackQueryHandler(step_16_handler, pattern=r"^wiz:freq:"),
            ],
            WizardStep.STEP_17_CONFIRM: [
                back_cancel_filter,
                CallbackQueryHandler(step_17_handler, pattern=r"^wiz:confirm:"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_command),
            CommandHandler("start", start_command),
        ],
        allow_reentry=True,
    )


@require_auth
async def start_edit_profile_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Load an existing profile owned by the user into the wizard draft for editing."""
    query = update.callback_query
    if query is None or query.data is None:
        return ConversationHandler.END
    profile_id = int(query.data.split(":")[2])
    user_id, _ = _ensure_user_and_settings(update, context)
    db: DatabaseManager = context.application.bot_data["db"]

    with db.session() as session:
        repo = SearchProfileRepository(session)
        profile = repo.get_profile(profile_id, user_id=user_id)

    if profile is None:
        await query.answer("⚠️ Profile not found or unauthorized.", show_alert=True)
        return ConversationHandler.END

    if context.user_data is not None:
        context.user_data.pop("wizard_draft", None)
    draft = _get_draft(context)
    f = profile.filters
    draft.update(
        {
            "edit_profile_id": profile.id,
            "name": profile.name,
            "auto_name": False,
            "makes": list(f.makes),
            "models": list(f.models),
            "fuels": [x.value for x in f.fuels],
            "body_styles": [x.value for x in f.body_styles],
            "drivetrains": [x.value for x in f.drivetrains],
            "off_road_preference": f.off_road_preference.value,
            "transmissions": [x.value for x in f.transmissions],
            "min_price_usd": f.min_price_usd,
            "max_price_usd": f.max_price_usd,
            "min_year": f.min_year,
            "max_year": f.max_year,
            "min_mileage_km": f.min_mileage_km,
            "max_mileage_km": f.max_mileage_km,
            "location": f.location,
            "customs_mode": f.customs_mode.value,
            "min_profit_usd": f.min_profit_usd,
            "min_deal_score": f.min_deal_score,
            "scan_frequency": f.scan_frequency.value,
        }
    )
    await query.answer("Editing search profile")
    return await render_step_1_name(update, context)
