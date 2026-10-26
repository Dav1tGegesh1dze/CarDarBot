from __future__ import annotations

import asyncio
import fcntl
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from cardarbot.config import Settings
from cardarbot.database.models import UserModel
from cardarbot.database.repositories import SearchProfileRepository
from cardarbot.database.session import DatabaseManager
from cardarbot.domain.enums import ScanFrequency
from cardarbot.domain.search_profiles import SearchProfileDomain
from cardarbot.services.search_service import SearchService

logger = logging.getLogger("cardarbot.services.scheduler")

FREQUENCY_HOURS_MAP: dict[ScanFrequency, int] = {
    ScanFrequency.DAILY: 24,
    ScanFrequency.EVERY_12_HOURS: 12,
    ScanFrequency.EVERY_6_HOURS: 6,
}


class ProcessLock:
    """File-based exclusive lock preventing duplicate polling or scanner instances on macOS."""

    def __init__(self, lock_path: Path | str = "data/cardarbot.lock") -> None:
        self.lock_path = Path(lock_path)
        self._fd: int | None = None

    def acquire(self) -> bool:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(str(self.lock_path), os.O_CREAT | os.O_RDWR, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.ftruncate(fd, 0)
            os.write(fd, f"{os.getpid()}\n".encode())
            self._fd = fd
            return True
        except OSError:
            return False

    def release(self) -> None:
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None


def is_profile_due_for_scan(profile: SearchProfileDomain, now: datetime | None = None) -> bool:
    """Determine if a search profile is due for a scheduled scan based on its ScanFrequency."""
    if not profile.is_active:
        return False
    if profile.filters.scan_frequency == ScanFrequency.MANUAL_ONLY:
        return False
    if profile.last_scanned_at is None:
        return True

    now_utc = now or datetime.now(UTC)
    last_utc = (
        profile.last_scanned_at
        if profile.last_scanned_at.tzinfo is not None
        else profile.last_scanned_at.replace(tzinfo=UTC)
    )
    interval_hours = FREQUENCY_HOURS_MAP.get(profile.filters.scan_frequency, 24)
    return (now_utc - last_utc) >= timedelta(hours=interval_hours)


class ScanScheduler:
    """Coordinated local scheduler running periodic profile checks with overlap protection and backoff."""

    def __init__(
        self,
        db: DatabaseManager,
        settings: Settings,
        search_service: SearchService | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.search_service = search_service or SearchService(db=db, settings=settings)
        self._scan_lock = asyncio.Lock()
        self._scheduler: AsyncIOScheduler | None = None

    async def tick_due_scans(self, bot: Any = None) -> int:
        """Check all active search profiles and run scans for those that are due."""
        if self._scan_lock.locked():
            logger.info("Scheduled scan tick skipped: previous scan is still running.")
            return 0

        async with self._scan_lock:
            with self.db.session() as session:
                p_repo = SearchProfileRepository(session)
                all_active = p_repo.list_all_active_profiles()
                user_map: dict[int, int] = {
                    u.id: u.telegram_user_id
                    for u in session.execute(select(UserModel)).scalars().all()
                }

            executed = 0
            now = datetime.now(UTC)
            for profile in all_active:
                if not is_profile_due_for_scan(profile, now=now):
                    continue
                tg_id = user_map.get(profile.user_id)
                if tg_id is None:
                    continue
                try:
                    await self.search_service.execute_profile_scan(
                        profile=profile,
                        telegram_user_id=tg_id,
                        bot=bot,
                        trigger_type="scheduled",
                    )
                    executed += 1
                except Exception as exc:
                    logger.error(
                        "Error executing scheduled scan for profile #%s: %s",
                        profile.id,
                        exc,
                    )
            return executed

    def start(self, bot: Any = None, check_interval_minutes: int = 30) -> None:
        """Start the AsyncIOScheduler background loop."""
        if self._scheduler is not None and self._scheduler.running:
            return
        self._scheduler = AsyncIOScheduler(timezone="Asia/Tbilisi")
        self._scheduler.add_job(
            self.tick_due_scans,
            trigger="interval",
            minutes=check_interval_minutes,
            kwargs={"bot": bot},
            id="cardarbot_periodic_scan",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.start()
        logger.info(
            "Started ScanScheduler (checking due profiles every %d minutes).",
            check_interval_minutes,
        )

    def shutdown(self) -> None:
        if self._scheduler is not None and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
