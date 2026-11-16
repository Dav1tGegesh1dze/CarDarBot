#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SERVICE_NAME="cardarbot"
SERVICE_USER="cardarbot"
SERVICE_HOME="/var/lib/${SERVICE_USER}"
UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

if [ "$(id -u)" -ne 0 ]; then
    echo "Error: run this script with sudo."
    exit 1
fi

cd "${PROJECT_DIR}"

echo "=== CarDarBot Linux Server Setup ==="

# 1. Require uv, which supplies the Python build the bot runs on
if ! command -v uv >/dev/null 2>&1; then
    echo "Error: uv is required. Install it system-wide first:"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sudo env UV_INSTALL_DIR=/usr/local/bin sh"
    exit 1
fi

# 2. Dedicated unprivileged user that owns the project directory
if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
    useradd --system --create-home --home-dir "${SERVICE_HOME}" \
        --shell /usr/sbin/nologin "${SERVICE_USER}"
    echo "Created system user: ${SERVICE_USER}"
fi

# 3. Prepare directories & .env
mkdir -p data logs
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "Created .env from .env.example."
    echo "IMPORTANT: Edit .env to add your TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USER_IDS."
fi
chmod 600 .env
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${PROJECT_DIR}"

as_service_user() {
    runuser -u "${SERVICE_USER}" -- "$@"
}

# 4. Create the virtual environment on uv's own Python 3.12 build, never the distribution's
#    python3: MyAuto.ge answers Ubuntu 24.04's system Python with a Cloudflare challenge.
if [ ! -d ".venv" ]; then
    as_service_user uv venv --seed --managed-python --python 3.12 .venv
fi
as_service_user .venv/bin/pip install --no-cache-dir -e .

# 5. Initialize SQLite database & run Alembic migrations
as_service_user .venv/bin/alembic upgrade head

# 6. Optional systemd installation (Only if --install-systemd flag is explicitly passed)
if [[ "${1:-}" == "--install-systemd" ]]; then
    cat > "${UNIT_PATH}" <<EOF
[Unit]
Description=CarDarBot Telegram bot and scheduled scanner
Wants=network-online.target
After=network-online.target

[Service]
User=${SERVICE_USER}
WorkingDirectory=${PROJECT_DIR}
ExecStart=${PROJECT_DIR}/.venv/bin/cardarbot run
Environment=PYTHONUNBUFFERED=1
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable --quiet "${SERVICE_NAME}"
    systemctl restart "${SERVICE_NAME}"
    echo "Installed and (re)started systemd service: ${UNIT_PATH}"
else
    echo ""
    echo "Setup complete! The systemd service was NOT installed automatically."
    echo "To install and start it (after configuring .env): sudo ./scripts/install_linux.sh --install-systemd"
fi
