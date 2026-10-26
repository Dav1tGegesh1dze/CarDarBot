from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from cardarbot.domain.enums import (
    BodyStyle,
    CustomsFilterMode,
    Drivetrain,
    FuelType,
    OffRoadPreference,
    ScanFrequency,
    Transmission,
)


class SearchFilterConfig(BaseModel):
    """Complete filter criteria for a user's saved car search."""

    makes: list[str] = Field(default_factory=list)  # Empty = Any
    models: list[str] = Field(default_factory=list)  # Empty = Any
    fuels: list[FuelType] = Field(default_factory=list)  # Empty = Any
    body_styles: list[BodyStyle] = Field(default_factory=list)  # Empty = Any
    drivetrains: list[Drivetrain] = Field(default_factory=list)  # Empty = Any
    off_road_preference: OffRoadPreference = OffRoadPreference.ANY
    transmissions: list[Transmission] = Field(default_factory=list)  # Empty = Any
    min_price_usd: int = Field(default=500, ge=0)
    max_price_usd: int = Field(default=5000, ge=100)
    min_year: int | None = Field(default=None, ge=1950, le=2030)
    max_year: int | None = Field(default=None, ge=1950, le=2030)
    min_mileage_km: int | None = Field(default=None, ge=0)
    max_mileage_km: int | None = Field(default=None, ge=0)
    location: str = "Tbilisi"
    customs_mode: CustomsFilterMode = CustomsFilterMode.CLEARED_ONLY
    min_profit_usd: int = Field(default=500, ge=0)
    min_deal_score: int = Field(default=70, ge=0, le=100)
    scan_frequency: ScanFrequency = ScanFrequency.DAILY

    @model_validator(mode="after")
    def validate_ranges(self) -> SearchFilterConfig:
        if self.min_price_usd > self.max_price_usd:
            raise ValueError("min_price_usd cannot exceed max_price_usd")
        if (
            self.min_year is not None
            and self.max_year is not None
            and self.min_year > self.max_year
        ):
            raise ValueError("min_year cannot exceed max_year")
        if (
            self.min_mileage_km is not None
            and self.max_mileage_km is not None
            and self.min_mileage_km > self.max_mileage_km
        ):
            raise ValueError("min_mileage_km cannot exceed max_mileage_km")
        return self

    def generate_auto_name(self) -> str:
        """Generate a descriptive search name automatically from configured filters."""
        parts: list[str] = []
        if self.makes:
            parts.append("/".join(self.makes[:2]))
        if self.models:
            parts.append("/".join(self.models[:2]))
        if self.fuels:
            fuel_labels = [f.value.replace("_", " ").title() for f in self.fuels[:2]]
            parts.append("/".join(fuel_labels))
        if self.body_styles:
            body_labels = [
                b.value.replace("_", "/").upper()
                if b == BodyStyle.SUV_CROSSOVER
                else b.value.title()
                for b in self.body_styles[:1]
            ]
            parts.append("/".join(body_labels))
        if not parts:
            parts.append("All Car")
        parts.append(f"Under ${self.max_price_usd:,}")
        return " ".join(parts)

    def format_summary(self, name: str) -> str:
        """Format the search configuration as a human-readable Telegram summary."""
        make_str = ", ".join(self.makes) if self.makes else "Any"
        model_str = ", ".join(self.models) if self.models else "Any"
        fuel_str = (
            ", ".join(f.value.replace("_", " ").title() for f in self.fuels)
            if self.fuels
            else "Any"
        )
        body_str = (
            ", ".join(b.value.replace("_", " ").title() for b in self.body_styles)
            if self.body_styles
            else "Any"
        )
        drive_str = (
            ", ".join(d.value.upper() for d in self.drivetrains) if self.drivetrains else "Any"
        )
        offroad_map = {
            OffRoadPreference.ANY: "Any",
            OffRoadPreference.AWD_4WD_PREFERRED: "AWD/4WD preferred",
            OffRoadPreference.AWD_4WD_REQUIRED: "AWD/4WD required",
            OffRoadPreference.VERIFIED_OFF_ROAD_MODEL: "Verified off-road model",
        }
        trans_str = (
            ", ".join(
                t.value.upper() if t == Transmission.CVT else t.value.title()
                for t in self.transmissions
            )
            if self.transmissions
            else "Any"
        )
        if self.min_year and self.max_year:
            year_str = f"{self.min_year}–{self.max_year}"
        elif self.min_year:
            year_str = f"{self.min_year}+"
        elif self.max_year:
            year_str = f"Up to {self.max_year}"
        else:
            year_str = "Any"

        if self.min_mileage_km is not None and self.max_mileage_km is not None:
            mileage_str = f"{self.min_mileage_km:,}–{self.max_mileage_km:,} km"
        elif self.max_mileage_km is not None:
            mileage_str = f"Up to {self.max_mileage_km:,} km"
        elif self.min_mileage_km is not None:
            mileage_str = f"{self.min_mileage_km:,}+ km"
        else:
            mileage_str = "Any"

        customs_map = {
            CustomsFilterMode.CLEARED_ONLY: "Cleared",
            CustomsFilterMode.INCLUDE_UNCLEARED: "Include uncleared",
            CustomsFilterMode.ANY: "Any",
        }
        freq_map = {
            ScanFrequency.DAILY: "Daily",
            ScanFrequency.EVERY_12_HOURS: "Every 12 hours",
            ScanFrequency.EVERY_6_HOURS: "Every 6 hours",
            ScanFrequency.MANUAL_ONLY: "Manual only",
        }

        return (
            f"🔎 {name}\n\n"
            f"Make: {make_str}\n"
            f"Model: {model_str}\n"
            f"Fuel: {fuel_str}\n"
            f"Body: {body_str}\n"
            f"Drivetrain: {drive_str}\n"
            f"Off-road: {offroad_map[self.off_road_preference]}\n"
            f"Transmission: {trans_str}\n"
            f"Price: ${self.min_price_usd:,}–${self.max_price_usd:,}\n"
            f"Year: {year_str}\n"
            f"Mileage: {mileage_str}\n"
            f"Location: {self.location}\n"
            f"Customs: {customs_map[self.customs_mode]}\n"
            f"Minimum profit: ${self.min_profit_usd:,}\n"
            f"Minimum score: {self.min_deal_score}\n"
            f"Frequency: {freq_map[self.scan_frequency]}"
        )


class SearchProfileDomain(BaseModel):
    """Domain representation of a persisted search profile."""

    id: int | None = None
    user_id: int
    name: str
    is_active: bool = True
    filters: SearchFilterConfig
    last_scanned_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
