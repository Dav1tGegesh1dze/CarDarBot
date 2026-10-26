from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from cardarbot.bot.handlers.search_wizard import (
    WizardStep,
    newsearch_entry,
    start_edit_profile_wizard,
    step_1_handler,
    step_2_handler,
    step_3_handler,
    step_4_handler,
    step_5_handler,
    step_6_handler,
    step_7_handler,
    step_8_handler,
    step_9_handler,
    step_10_handler,
    step_11_handler,
    step_12_handler,
    step_13_handler,
    step_14_handler,
    step_15_handler,
    step_16_handler,
    step_17_handler,
)
from cardarbot.bot.handlers.searches import (
    natural_language_callback_handler,
    natural_language_message_handler,
    search_action_callback_handler,
    searches_command,
)
from cardarbot.bot.natural_language import parse_natural_language_search
from cardarbot.config import Settings
from cardarbot.database.repositories import SearchProfileRepository
from cardarbot.database.session import DatabaseManager
from cardarbot.domain.enums import (
    BodyStyle,
    Drivetrain,
    FuelType,
    OffRoadPreference,
)


def _setup_ctx(user_id: int = 888001) -> tuple[MagicMock, MagicMock, DatabaseManager]:
    db = DatabaseManager("sqlite:///:memory:")
    db.init_db()
    settings = Settings(
        TELEGRAM_BOT_TOKEN="123456789:ABCDEF1234567890abcdef1234567890",
        TELEGRAM_ALLOWED_USER_IDS=[user_id, 888002],
    )
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.username = "carbuyer"
    update.effective_user.first_name = "Davit"
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.effective_message = MagicMock()
    update.effective_message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {}
    context.application.bot_data = {"settings": settings, "db": db}
    context.bot = AsyncMock()
    return update, context, db


def test_natural_language_search_parser() -> None:
    p1 = parse_natural_language_search("Find Toyota Prius under $4000")
    assert p1.is_confident is True
    assert p1.filters.makes == ["Toyota"]
    assert p1.filters.models == ["Prius"]
    assert p1.filters.max_price_usd == 4000

    p2 = parse_natural_language_search("Electric cars under $5000")
    assert p2.is_confident is True
    assert p2.filters.fuels == [FuelType.ELECTRIC]
    assert FuelType.HYBRID not in p2.filters.fuels

    p3 = parse_natural_language_search("BMW coupe 2012-2018")
    assert p3.is_confident is True
    assert p3.filters.makes == ["BMW"]
    assert p3.filters.body_styles == [BodyStyle.COUPE]
    assert p3.filters.min_year == 2012
    assert p3.filters.max_year == 2018

    p4 = parse_natural_language_search("Hybrid SUVs in Tbilisi")
    assert p4.is_confident is True
    assert p4.filters.fuels == [FuelType.HYBRID]
    assert p4.filters.body_styles == [BodyStyle.SUV_CROSSOVER]
    # Invariant: Do not treat every SUV as an off-road vehicle
    assert p4.filters.off_road_preference == OffRoadPreference.ANY

    p5 = parse_natural_language_search("Find 4x4 under $3000")
    assert p5.is_confident is True
    assert Drivetrain.FOUR_WD in p5.filters.drivetrains
    assert p5.filters.max_price_usd == 3000

    # Uncertain text
    p6 = parse_natural_language_search("Hello how are you today")
    assert p6.is_confident is False


@pytest.mark.asyncio
async def test_full_17_step_wizard_and_profile_management() -> None:
    update, ctx, db = _setup_ctx(888001)

    # Start wizard
    state = await newsearch_entry(update, ctx)
    assert state == WizardStep.STEP_1_NAME

    # Step 1: Name
    update.callback_query.data = "wiz:name:Toyota Hybrid Deals"
    assert await step_1_handler(update, ctx) == WizardStep.STEP_2_MANUFACTURER

    # Step 2: Make (select Toyota then Next)
    update.callback_query.data = "wiz:make:Toyota"
    assert await step_2_handler(update, ctx) == WizardStep.STEP_2_MANUFACTURER
    update.callback_query.data = "wiz:make:NEXT"
    assert await step_2_handler(update, ctx) == WizardStep.STEP_3_MODEL

    # Step 3: Model (invalid model via text rejected, then valid Prius via callback)
    update.callback_query = None
    update.effective_message.text = "X5"
    assert await step_3_handler(update, ctx) == WizardStep.STEP_3_MODEL
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.data = "wiz:model:Prius"
    assert await step_3_handler(update, ctx) == WizardStep.STEP_3_MODEL
    update.callback_query.data = "wiz:model:NEXT"
    assert await step_3_handler(update, ctx) == WizardStep.STEP_4_FUEL

    # Step 4: Fuel (Hybrid group)
    update.callback_query.data = "wiz:fuelgrp:hybrid"
    assert await step_4_handler(update, ctx) == WizardStep.STEP_4_FUEL
    update.callback_query.data = "wiz:fuel:NEXT"
    assert await step_4_handler(update, ctx) == WizardStep.STEP_5_BODY

    # Step 5: Body (Hatchback)
    update.callback_query.data = "wiz:body:hatchback"
    assert await step_5_handler(update, ctx) == WizardStep.STEP_5_BODY
    update.callback_query.data = "wiz:body:NEXT"
    assert await step_5_handler(update, ctx) == WizardStep.STEP_6_DRIVETRAIN

    # Step 6: Drivetrain (FWD)
    update.callback_query.data = "wiz:drive:fwd"
    assert await step_6_handler(update, ctx) == WizardStep.STEP_6_DRIVETRAIN
    update.callback_query.data = "wiz:drive:NEXT"
    assert await step_6_handler(update, ctx) == WizardStep.STEP_7_OFFROAD

    # Step 7: Off-road
    update.callback_query.data = "wiz:offroad:any"
    assert await step_7_handler(update, ctx) == WizardStep.STEP_8_TRANSMISSION

    # Step 8: Transmission
    update.callback_query.data = "wiz:trans:ANY"
    assert await step_8_handler(update, ctx) == WizardStep.STEP_9_BUDGET

    # Step 9: Budget
    update.callback_query.data = "wiz:budget:500_4800"
    assert await step_9_handler(update, ctx) == WizardStep.STEP_10_YEAR

    # Step 10: Year
    update.callback_query.data = "wiz:year:2010_2017"
    assert await step_10_handler(update, ctx) == WizardStep.STEP_11_MILEAGE

    # Step 11: Mileage (test miles to km conversion via text: 100,000 mi -> ~160,934 km)
    update.callback_query = None
    update.effective_message.text = "100000 mi"
    assert await step_11_handler(update, ctx) == WizardStep.STEP_12_LOCATION
    assert ctx.user_data["wizard_draft"]["max_mileage_km"] == 160934

    # Step 12: Location
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.data = "wiz:loc:Tbilisi"
    assert await step_12_handler(update, ctx) == WizardStep.STEP_13_CUSTOMS

    # Step 13: Customs
    update.callback_query.data = "wiz:customs:cleared_only"
    assert await step_13_handler(update, ctx) == WizardStep.STEP_14_MIN_PROFIT

    # Step 14: Profit
    update.callback_query.data = "wiz:profit:500"
    assert await step_14_handler(update, ctx) == WizardStep.STEP_15_DEAL_SCORE

    # Step 15: Score
    update.callback_query.data = "wiz:score:70"
    assert await step_15_handler(update, ctx) == WizardStep.STEP_16_FREQUENCY

    # Step 16: Frequency
    update.callback_query.data = "wiz:freq:daily"
    assert await step_16_handler(update, ctx) == WizardStep.STEP_17_CONFIRM

    # Verify profile is NOT persisted before confirmation
    with db.session() as session:
        repo = SearchProfileRepository(session)
        assert len(repo.list_all_active_profiles()) == 0

    # Step 17: Save and Activate
    update.callback_query.data = "wiz:confirm:SAVE"
    await step_17_handler(update, ctx)

    with db.session() as session:
        repo = SearchProfileRepository(session)
        profiles = repo.list_all_active_profiles()
        assert len(profiles) == 1
        pid = profiles[0].id
        assert pid is not None
        assert profiles[0].name == "Toyota Hybrid Deals"
        assert profiles[0].filters.max_price_usd == 4800

    # Test /searches management: view, pause, resume, duplicate, edit, delete
    await searches_command(update, ctx)

    update.callback_query.data = f"srch:pause:{pid}"
    await search_action_callback_handler(update, ctx)
    assert "Paused" in update.callback_query.edit_message_text.call_args.kwargs["text"]

    update.callback_query.data = f"srch:resume:{pid}"
    await search_action_callback_handler(update, ctx)
    assert "Active" in update.callback_query.edit_message_text.call_args.kwargs["text"]

    update.callback_query.data = f"srch:dup:{pid}"
    await search_action_callback_handler(update, ctx)
    assert "(Copy)" in update.callback_query.edit_message_text.call_args.kwargs["text"]

    # Edit existing profile
    update.callback_query.data = f"srch:edit:{pid}"
    assert await start_edit_profile_wizard(update, ctx) == WizardStep.STEP_1_NAME
    assert ctx.user_data["wizard_draft"]["edit_profile_id"] == pid

    # Delete confirmation flow
    update.callback_query.data = f"srch:delask:{pid}"
    await search_action_callback_handler(update, ctx)
    assert (
        "Are you sure" in update.callback_query.edit_message_text.call_args.kwargs[0]
        if not update.callback_query.edit_message_text.call_args.args
        else update.callback_query.edit_message_text.call_args.args[0]
    )

    update.callback_query.data = f"srch:delconfirm:{pid}"
    await search_action_callback_handler(update, ctx)

    # Verify natural language message & save flow
    update.callback_query = None
    update.effective_message.text = "Electric cars under $5000"
    await natural_language_message_handler(update, ctx)
    assert "Natural Language Search Draft" in (update.effective_message.reply_text.call_args[0][0])

    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.data = "nl:save"
    await natural_language_callback_handler(update, ctx)
    assert "Saved Search" in update.callback_query.edit_message_text.call_args[0][0]
