from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from cardarbot.config import get_settings
from cardarbot.database.session import DatabaseManager
from cardarbot.services.deal_service import DealService
from cardarbot.services.scheduler import ProcessLock, ScanScheduler
from cardarbot.services.search_service import SearchService
from cardarbot.sources.import_adapter import ListingImportAdapter
from cardarbot.utils.logging import setup_logging


def run_bot() -> int:
    """Acquire exclusive process lock, initialize database, start scheduler and Telegram polling."""
    settings = get_settings()
    settings.ensure_directories()
    token_secret = settings.telegram_bot_token.get_secret_value().strip()
    logger = setup_logging(
        level=settings.log_level,
        log_file=Path("logs/cardarbot.log"),
        secrets_to_redact=[token_secret] if token_secret else None,
    )

    lock = ProcessLock("data/cardarbot.lock")
    if not lock.acquire():
        logger.error(
            "Another CarDarBot instance is already running (lock held on data/cardarbot.lock). Exiting."
        )
        return 1

    try:
        db = DatabaseManager(settings.database_url)
        db.init_db()

        if not settings.has_valid_bot_token():
            logger.error(
                "TELEGRAM_BOT_TOKEN is missing or invalid. Please configure a newly generated "
                "BotFather token in your local .env file before starting live polling."
            )
            return 1

        if not settings.telegram_allowed_user_ids:
            logger.warning(
                "TELEGRAM_ALLOWED_USER_IDS is empty! Private access is enforced by default; "
                "all incoming Telegram messages will be rejected until your user ID is added to .env."
            )

        from cardarbot.bot.app import create_bot_application

        app = create_bot_application(settings=settings, db=db)
        scheduler = ScanScheduler(
            db=db,
            settings=settings,
            search_service=app.bot_data.get("search_service"),
        )
        app.bot_data["scheduler"] = scheduler

        logger.info("Starting CarDarBot polling and coordinated scheduler...")
        app.run_polling(drop_pending_updates=True)
        return 0
    finally:
        lock.release()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cardarbot",
        description="CarDarBot — Georgian Undervalued Used Car Finder & Telegram Bot",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("run", help="Start the Telegram bot and scheduled scanner")
    subparsers.add_parser("init-db", help="Initialize the SQLite database schema")
    subparsers.add_parser("check-config", help="Validate .env configuration safely")
    subparsers.add_parser("scan-once", help="Run all active scheduled searches once and exit")

    import_parser = subparsers.add_parser(
        "import-file", help="Import and evaluate listings from a .json, .csv, or .html file"
    )
    import_parser.add_argument("path", help="Path to .json, .csv, or .html file")

    args = parser.parse_args(argv)
    settings = get_settings()
    settings.ensure_directories()
    token_secret = settings.telegram_bot_token.get_secret_value().strip()
    setup_logging(
        level=settings.log_level,
        log_file=Path("logs/cardarbot.log"),
        secrets_to_redact=[token_secret] if token_secret else None,
    )

    if args.command == "init-db":
        db = DatabaseManager(settings.database_url)
        db.init_db()
        print(f"Database initialized at {settings.database_url}")
        return 0

    if args.command == "check-config":
        print(f"City: {settings.default_city}")
        print(f"Max Price USD: ${settings.default_max_price_usd:,}")
        print(f"Min Profit USD: ${settings.default_min_profit_usd:,}")
        print(f"Min Deal Score: {settings.default_min_deal_score}/100")
        print(f"Allowed User IDs: {settings.telegram_allowed_user_ids}")
        print(f"Token Configured: {'Yes' if settings.has_valid_bot_token() else 'No'}")
        return 0

    if args.command == "import-file":
        db = DatabaseManager(settings.database_url)
        db.init_db()
        adapter = ListingImportAdapter(
            gel_to_usd_rate=settings.gel_to_usd_rate,
            eur_to_usd_rate=settings.eur_to_usd_rate,
        )
        res = adapter.import_from_file(args.path)
        if res.error_message:
            print(f"Import error: {res.error_message}")
            return 1
        deal_service = DealService(db=db, settings=settings)
        evaluated = deal_service.ingest_and_evaluate_listings(res.listings)
        print(f"Imported and evaluated {len(evaluated)} listings from {args.path}.")
        return 0

    if args.command == "scan-once":
        db = DatabaseManager(settings.database_url)
        db.init_db()
        svc = SearchService(db=db, settings=settings)
        count = asyncio.run(svc.run_all_active_profiles_scheduled(bot=None))
        print(f"Executed scheduled scan across {count} active profile(s).")
        return 0

    return run_bot()


if __name__ == "__main__":
    sys.exit(main())
