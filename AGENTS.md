# CarDarBot — Architecture & Agent Developer Guide

## Overview
**CarDarBot** (`@CarDar_Georgia_bot`) is a configurable Telegram bot and analytical engine that discovers undervalued used vehicles in Georgia (primarily Tbilisi via MyAuto.ge and structured import pipelines) and evaluates potential resale profit.

## Clean Architecture Boundaries
- `src/cardarbot/config.py`: Environment & runtime settings (`pydantic-settings`). Never logs or exposes secrets (`TELEGRAM_BOT_TOKEN`).
- `src/cardarbot/domain/`: Pure domain enums, data transfer models, manufacturer/model catalog, and validation logic.
- `src/cardarbot/database/`: SQLAlchemy 2.x models, SQLite WAL session management, and repositories.
- `src/cardarbot/sources/`: Pluggable listing sources (`base.py`, `myauto.py`, `import_adapter.py`) with explicit source health and operational mode tracking (`LIVE`, `IMPORT_ONLY`, `TEMPORARILY_UNAVAILABLE`, `UNSUPPORTED`).
- `src/cardarbot/analysis/`:
  - `normalization.py`: Trilingual (Georgian/English/Russian) text normalization, mileage/currency normalization.
  - `spam_filter.py`: Layered spam, placeholder price, parts-only, down-payment, and major mechanical damage detector with explicit rejection reasons.
  - `comparables.py`: Robust statistical market value estimator using median/quantiles and configurable resale discount.
  - `profit.py`: Full net profit calculator incorporating inspection, repair, detailing, registration, and contingency buffers.
  - `scoring.py`: Transparent 0–100 deal scoring with weighted breakdown and classification.
- `src/cardarbot/services/`: Orchestration layer (`search_service.py`, `deal_service.py`, `notification_service.py`, `scheduler.py`).
- `src/cardarbot/bot/`: `python-telegram-bot` v21+ handlers, inline keyboards, conversation wizards, natural language parser, and authorization middleware.

## Security & Operational Invariants
1. **Token Protection**: `TELEGRAM_BOT_TOKEN` is loaded exclusively from `.env` or environment variables using `SecretStr` and masked in logs.
2. **Private Access by Default**: Only Telegram user IDs listed in `TELEGRAM_ALLOWED_USER_IDS` can interact with the bot.
3. **No Fabricated Data**: Never invent API endpoints, fake listings, or fabricated comparables. If `myauto.ge` enforces Cloudflare Turnstile/JS challenge, report status accurately as `TEMPORARILY_UNAVAILABLE` / `IMPORT_ONLY` and allow seamless JSON/CSV/HTML/URL import via CLI or Telegram document upload.
4. **Database Concurrency**: SQLite runs with `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=NORMAL`, and `PRAGMA foreign_keys=ON`. All stored timestamps use UTC; user-facing displays convert to `Asia/Tbilisi`.
