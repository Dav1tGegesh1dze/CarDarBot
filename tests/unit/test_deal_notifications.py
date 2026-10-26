from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from cardarbot.bot.handlers.deals import (
    deal_callback_handler,
    deals_command,
    saved_command,
)
from cardarbot.config import Settings
from cardarbot.database.repositories import SearchProfileRepository, UserRepository
from cardarbot.database.session import DatabaseManager
from cardarbot.domain.enums import CustomsStatus, FuelType, SourceStatusMode
from cardarbot.domain.search_profiles import SearchFilterConfig
from cardarbot.domain.vehicles import NormalizedListing
from cardarbot.services.search_service import SearchService
from cardarbot.sources.base import BaseListingSource, SourceFetchResult


class MockLiveListingSource(BaseListingSource):
    source_name = "myauto"

    def __init__(self, items: list[NormalizedListing]) -> None:
        self._items = items

    async def fetch_listings(
        self, filters: SearchFilterConfig | None = None, max_pages: int = 1
    ) -> SourceFetchResult:
        return SourceFetchResult(
            source_name=self.source_name,
            status_mode=SourceStatusMode.LIVE,
            listings=self._items,
        )


def _sample_listings() -> list[NormalizedListing]:
    # 5 market comparables around $4,900 - $5,100 + 1 undervalued candidate at $3,200
    items: list[NormalizedListing] = []
    for idx, price in enumerate([4900.0, 5000.0, 5100.0, 5050.0, 4950.0], start=1):
        items.append(
            NormalizedListing(
                source="myauto",
                source_listing_id=f"comp_{idx}",
                url=f"https://www.myauto.ge/ka/pr/comp_{idx}",
                make="Toyota",
                model="Prius",
                year=2013,
                fuel=FuelType.HYBRID,
                powertrain="hybrid",
                mileage_km=150000 + idx * 3000,
                location="Tbilisi",
                customs_status=CustomsStatus.CLEARED,
                price=price,
                currency="USD",
                usd_price=price,
                description="განბაჟებულია, კარგ მდგომარეობაში",
            )
        )
    # Candidate deal at $3,200
    items.append(
        NormalizedListing(
            source="myauto",
            source_listing_id="flip_candidate_1",
            url="https://www.myauto.ge/ka/pr/flip_candidate_1",
            make="Toyota",
            model="Prius",
            year=2013,
            fuel=FuelType.HYBRID,
            powertrain="hybrid",
            mileage_km=152000,
            location="Tbilisi",
            customs_status=CustomsStatus.CLEARED,
            price=3200.0,
            currency="USD",
            usd_price=3200.0,
            description="სასწრაფოდ! განბაჟებულია, იდეალურ მდგომარეობაში",
        )
    )
    return items


@pytest.mark.asyncio
async def test_deal_notifications_deduplication_and_browsing() -> None:
    db = DatabaseManager("sqlite:///:memory:")
    db.init_db()
    settings = Settings(
        TELEGRAM_BOT_TOKEN="123456789:ABCDEF1234567890abcdef1234567890",
        TELEGRAM_ALLOWED_USER_IDS=[999001],
    )

    with db.session() as session:
        u_repo = UserRepository(session)
        p_repo = SearchProfileRepository(session)
        user = u_repo.get_or_create_user(telegram_user_id=999001, username="flipper")
        profile = p_repo.create_profile(
            user.id,
            "Toyota Hybrid Deals",
            SearchFilterConfig(
                makes=["Toyota"],
                models=["Prius"],
                fuels=[FuelType.HYBRID],
                max_price_usd=4500,
                min_profit_usd=500,
                min_deal_score=70,
            ),
        )

    mock_bot = AsyncMock()
    items = _sample_listings()
    source = MockLiveListingSource(items)
    search_service = SearchService(db=db, settings=settings, source=source)

    # First scan: sends 1 notification for flip_candidate_1 ($3,200)
    stats1 = await search_service.execute_profile_scan(
        profile=profile,
        telegram_user_id=999001,
        bot=mock_bot,
        trigger_type="manual",
    )
    assert stats1["deals_found"] == 1
    assert stats1["alerts_sent"] == 1
    mock_bot.send_message.assert_awaited_once()
    sent_text = mock_bot.send_message.call_args.kwargs["text"]
    assert "💎 POTENTIAL CAR FLIP" in sent_text
    assert "Toyota Prius 2013" in sent_text
    assert "Asking price: $3,200" in sent_text
    assert "Matched search:\nToyota Hybrid Deals" in sent_text

    # Second scan with identical price: duplicate notification is prevented
    mock_bot.send_message.reset_mock()
    stats2 = await search_service.execute_profile_scan(
        profile=profile,
        telegram_user_id=999001,
        bot=mock_bot,
        trigger_type="manual",
    )
    assert stats2["deals_found"] == 1
    assert stats2["alerts_sent"] == 0
    mock_bot.send_message.assert_not_awaited()

    # Third scan after meaningful price drop ($3,200 -> $2,950): triggers price-drop alert
    items[-1].price = 2950.0
    items[-1].usd_price = 2950.0
    stats3 = await search_service.execute_profile_scan(
        profile=profile,
        telegram_user_id=999001,
        bot=mock_bot,
        trigger_type="manual",
    )
    assert stats3["alerts_sent"] == 1
    drop_text = mock_bot.send_message.call_args.kwargs["text"]
    assert "PRICE DROP" in drop_text

    # Test /deals, detail, comparables, price history, save, and dismiss via Telegram handlers
    update = MagicMock()
    update.effective_user.id = 999001
    update.effective_user.username = "flipper"
    update.effective_user.first_name = "Flipper"
    update.callback_query = None
    update.effective_message = MagicMock()
    update.effective_message.reply_text = AsyncMock()

    ctx = MagicMock()
    ctx.user_data = {}
    ctx.application.bot_data = {
        "settings": settings,
        "db": db,
        "search_service": search_service,
    }
    ctx.bot = mock_bot

    await deals_command(update, ctx)
    assert "Deal Browser" in update.effective_message.reply_text.call_args.kwargs["text"]

    # Callback queries for listing #6 (flip_candidate_1)
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()

    for action_cb, expected_substr in [
        ("deal:detail:6", "Vehicle Evaluation Details"),
        ("deal:comps:6", "Comparable Vehicles"),
        ("deal:history:6", "Price History"),
    ]:
        update.callback_query.data = action_cb
        await deal_callback_handler(update, ctx)
        assert expected_substr in update.callback_query.edit_message_text.call_args.kwargs["text"]

    # Save listing #6 and check /saved
    update.callback_query.data = "deal:save:6"
    await deal_callback_handler(update, ctx)
    await saved_command(update, ctx)
    assert "Saved Cars" in update.callback_query.edit_message_text.call_args.kwargs["text"]

    # Dismiss listing #6
    update.callback_query.data = "deal:dismiss:6"
    await deal_callback_handler(update, ctx)
    assert "Dismissed" in update.callback_query.edit_message_text.call_args[0][0]
