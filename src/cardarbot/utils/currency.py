from __future__ import annotations

from enum import StrEnum

# National Bank of Georgia reference rates (documented baseline, configurable via Settings)
DEFAULT_RATES_TO_USD: dict[str, float] = {
    "USD": 1.0,
    "$": 1.0,
    "GEL": 0.3676,  # ~2.72 GEL per 1 USD
    "₾": 0.3676,
    "EUR": 1.08,
    "€": 1.08,
}


class SupportedCurrency(StrEnum):
    USD = "USD"
    GEL = "GEL"
    EUR = "EUR"


def normalize_currency_code(raw: str | None) -> str:
    """Normalize currency symbols or strings to standard ISO 4217 code."""
    if not raw:
        return "USD"
    folded = raw.strip().casefold()
    mapping = {
        "$": "USD",
        "usd": "USD",
        "us$": "USD",
        "დოლარი": "USD",
        "₾": "GEL",
        "gel": "GEL",
        "ლარი": "GEL",
        "ლ": "GEL",
        "€": "EUR",
        "eur": "EUR",
        "ევრო": "EUR",
    }
    if folded in mapping:
        return mapping[folded]
    upper = raw.strip().upper()
    return upper if upper in {"USD", "GEL", "EUR"} else "UNKNOWN"


def convert_to_usd(
    amount: float | int | None,
    currency: str | None,
    gel_to_usd: float = 0.3676,
    eur_to_usd: float = 1.08,
) -> float | None:
    """Convert a price in USD, GEL, or EUR into USD rounded to 2 decimal places."""
    if amount is None or amount < 0:
        return None
    code = normalize_currency_code(currency)
    if code == "USD":
        return round(float(amount), 2)
    if code == "GEL":
        return round(float(amount) * gel_to_usd, 2)
    if code == "EUR":
        return round(float(amount) * eur_to_usd, 2)
    return None
