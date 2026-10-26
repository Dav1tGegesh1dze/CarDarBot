from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from cardarbot.config import Settings
from cardarbot.database.repositories import SearchProfileRepository, UserRepository
from cardarbot.database.session import DatabaseManager
from cardarbot.domain.enums import ScanFrequency
from cardarbot.domain.search_profiles import SearchFilterConfig, SearchProfileDomain
from cardarbot.services.scheduler import (
    ProcessLock,
    ScanScheduler,
    is_profile_due_for_scan,
)


def test_process_lock_prevents_duplicate_instances(tmp_path: Path) -> None:
    lock_file = tmp_path / "test_bot.lock"
    lock1 = ProcessLock(lock_file)
    lock2 = ProcessLock(lock_file)

    assert lock1.acquire() is True
    assert lock2.acquire() is False
    lock1.release()
    assert lock2.acquire() is True
    lock2.release()


def test_is_profile_due_for_scan() -> None:
    now = datetime.now(UTC)

    # Never scanned -> due
    p_never = SearchProfileDomain(
        id=1,
        user_id=1,
        name="Daily Search",
        is_active=True,
        filters=SearchFilterConfig(scan_frequency=ScanFrequency.DAILY),
        last_scanned_at=None,
    )
    assert is_profile_due_for_scan(p_never, now=now) is True

    # Scanned 2 hours ago on Daily schedule -> not due
    p_recent = p_never.model_copy(update={"last_scanned_at": now - timedelta(hours=2)})
    assert is_profile_due_for_scan(p_recent, now=now) is False

    # Scanned 25 hours ago on Daily schedule -> due
    p_old = p_never.model_copy(update={"last_scanned_at": now - timedelta(hours=25)})
    assert is_profile_due_for_scan(p_old, now=now) is True

    # Manual-only -> never due for automatic scheduled scan
    p_manual = SearchProfileDomain(
        id=2,
        user_id=1,
        name="Manual Search",
        is_active=True,
        filters=SearchFilterConfig(scan_frequency=ScanFrequency.MANUAL_ONLY),
        last_scanned_at=None,
    )
    assert is_profile_due_for_scan(p_manual, now=now) is False


@pytest.mark.asyncio
async def test_scan_scheduler_tick_and_lifecycle() -> None:
    db = DatabaseManager("sqlite:///:memory:")
    db.init_db()
    settings = Settings(TELEGRAM_ALLOWED_USER_IDS=[777111])

    with db.session() as session:
        u_repo = UserRepository(session)
        p_repo = SearchProfileRepository(session)
        u = u_repo.get_or_create_user(telegram_user_id=777111)
        p_repo.create_profile(
            u.id,
            "Daily Toyota",
            SearchFilterConfig(makes=["Toyota"], scan_frequency=ScanFrequency.DAILY),
        )

    mock_search_service = AsyncMock()
    mock_search_service.execute_profile_scan.return_value = {"deals_found": 0}
    scheduler = ScanScheduler(
        db=db,
        settings=settings,
        search_service=mock_search_service,
    )

    executed = await scheduler.tick_due_scans(bot=None)
    assert executed == 1
    mock_search_service.execute_profile_scan.assert_awaited_once()

    scheduler.start(bot=None, check_interval_minutes=60)
    scheduler.shutdown()
