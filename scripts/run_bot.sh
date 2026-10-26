#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

mkdir -p data logs

if [ ! -d ".venv" ]; then
    echo "Error: Virtual environment .venv not found in ${PROJECT_DIR}."
    echo "Run ./scripts/install_mac.sh first."
    exit 1
fi

if [ ! -f ".env" ]; then
    echo "Error: .env file not found in ${PROJECT_DIR}."
    echo "Copy .env.example to .env and configure TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USER_IDS."
    exit 1
fi

exec "${PROJECT_DIR}/.venv/bin/cardarbot" run
