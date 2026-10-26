from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from cardarbot.bot.callbacks import (
    CB_CANCEL,
    CB_MAIN_MENU,
    CB_MENU_BEST_DEALS,
    CB_MENU_CREATE_SEARCH,
    CB_MENU_HELP,
    CB_MENU_MARKET_OVERVIEW,
    CB_MENU_MY_SEARCHES,
    CB_MENU_SAVED_CARS,
    CB_MENU_SETTINGS,
    CB_SET_ALERT_LIMIT,
    CB_SET_CITY,
    CB_SET_CURRENCY,
    CB_SET_DAILY_SUMMARY,
    CB_SET_LANGUAGE,
    CB_SET_MAX_PRICE,
    CB_SET_MIN_PROFIT,
    CB_SET_NOTIFICATIONS,
    CB_SET_QUIET_HOURS,
    CB_SET_SCORE,
)
from cardarbot.database.models import UserSettingsModel


def build_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Build the primary CarDarBot Telegram inline keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("🔎 Create Search", callback_data=CB_MENU_CREATE_SEARCH),
            InlineKeyboardButton("🚘 My Searches", callback_data=CB_MENU_MY_SEARCHES),
        ],
        [
            InlineKeyboardButton("💎 Best Deals", callback_data=CB_MENU_BEST_DEALS),
            InlineKeyboardButton("⭐ Saved Cars", callback_data=CB_MENU_SAVED_CARS),
        ],
        [
            InlineKeyboardButton("📊 Market Overview", callback_data=CB_MENU_MARKET_OVERVIEW),
            InlineKeyboardButton("⚙️ Settings", callback_data=CB_MENU_SETTINGS),
        ],
        [
            InlineKeyboardButton("❓ Help", callback_data=CB_MENU_HELP),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_back_to_main_keyboard() -> InlineKeyboardMarkup:
    """Build a simple navigation keyboard returning to the Main Menu."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🏠 Main Menu", callback_data=CB_MAIN_MENU)]]
    )


def build_settings_keyboard(settings: UserSettingsModel) -> InlineKeyboardMarkup:
    """Build interactive settings keyboard reflecting current user settings."""
    notif_label = (
        "🔔 Notifications: ON" if settings.notifications_enabled else "🔕 Notifications: OFF"
    )
    summary_label = (
        "📅 Daily Summary: ON" if settings.daily_summary_enabled else "📅 Daily Summary: OFF"
    )
    if settings.quiet_hours_start is not None and settings.quiet_hours_end is not None:
        quiet_label = (
            f"🌙 Quiet Hours: {settings.quiet_hours_start:02d}:00–{settings.quiet_hours_end:02d}:00"
        )
    else:
        quiet_label = "🌙 Quiet Hours: Off"

    keyboard = [
        [
            InlineKeyboardButton(
                f"💰 Max Price: ${settings.default_max_price_usd:,}",
                callback_data=CB_SET_MAX_PRICE,
            ),
            InlineKeyboardButton(
                f"💵 Min Profit: ${settings.default_min_profit_usd:,}",
                callback_data=CB_SET_MIN_PROFIT,
            ),
        ],
        [
            InlineKeyboardButton(
                f"📍 City: {settings.default_city}",
                callback_data=CB_SET_CITY,
            ),
            InlineKeyboardButton(
                f"⭐ Min Score: {settings.default_min_score}/100",
                callback_data=CB_SET_SCORE,
            ),
        ],
        [
            InlineKeyboardButton(
                f"💱 Currency: {settings.preferred_currency}",
                callback_data=CB_SET_CURRENCY,
            ),
            InlineKeyboardButton(
                f"🚨 Alert Limit: {settings.max_alerts_per_scan}/scan",
                callback_data=CB_SET_ALERT_LIMIT,
            ),
        ],
        [
            InlineKeyboardButton(notif_label, callback_data=CB_SET_NOTIFICATIONS),
            InlineKeyboardButton(summary_label, callback_data=CB_SET_DAILY_SUMMARY),
        ],
        [
            InlineKeyboardButton(quiet_label, callback_data=CB_SET_QUIET_HOURS),
            InlineKeyboardButton(
                f"🌐 Language: {settings.preferred_language.upper()}",
                callback_data=CB_SET_LANGUAGE,
            ),
        ],
        [
            InlineKeyboardButton("🏠 Main Menu", callback_data=CB_MAIN_MENU),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_settings_preset_keyboard(setting_type: str) -> InlineKeyboardMarkup:
    """Build preset selection buttons for a specific setting."""
    rows: list[list[InlineKeyboardButton]] = []
    if setting_type == CB_SET_MAX_PRICE:
        for val in [3000, 5000, 7500, 10000, 15000]:
            rows.append(
                [InlineKeyboardButton(f"${val:,}", callback_data=f"setval:max_price:{val}")]
            )
    elif setting_type == CB_SET_MIN_PROFIT:
        for val in [300, 500, 750, 1000, 1500]:
            rows.append(
                [InlineKeyboardButton(f"${val:,}", callback_data=f"setval:min_profit:{val}")]
            )
    elif setting_type == CB_SET_SCORE:
        for val in [55, 65, 70, 75, 85]:
            rows.append([InlineKeyboardButton(f"{val}/100", callback_data=f"setval:score:{val}")])
    elif setting_type == CB_SET_CURRENCY:
        for cur in ["USD", "GEL", "EUR"]:
            rows.append([InlineKeyboardButton(cur, callback_data=f"setval:currency:{cur}")])
    elif setting_type == CB_SET_ALERT_LIMIT:
        for lim in [5, 10, 20, 50]:
            rows.append(
                [InlineKeyboardButton(f"{lim} per scan", callback_data=f"setval:limit:{lim}")]
            )
    elif setting_type == CB_SET_QUIET_HOURS:
        rows.append([InlineKeyboardButton("23:00 – 08:00", callback_data="setval:quiet:23_8")])
        rows.append([InlineKeyboardButton("22:00 – 07:00", callback_data="setval:quiet:22_7")])
        rows.append([InlineKeyboardButton("Disable Quiet Hours", callback_data="setval:quiet:off")])
    elif setting_type == CB_SET_LANGUAGE:
        rows.append([InlineKeyboardButton("English (EN)", callback_data="setval:lang:en")])
        rows.append(
            [InlineKeyboardButton("ქართული (KA - Preview)", callback_data="setval:lang:ka")]
        )
    elif setting_type == CB_SET_CITY:
        rows.append(
            [InlineKeyboardButton("Tbilisi (Default)", callback_data="setval:city:Tbilisi")]
        )

    rows.append(
        [
            InlineKeyboardButton("⬅️ Back to Settings", callback_data=CB_MENU_SETTINGS),
            InlineKeyboardButton("❌ Cancel", callback_data=CB_CANCEL),
        ]
    )
    return InlineKeyboardMarkup(rows)
