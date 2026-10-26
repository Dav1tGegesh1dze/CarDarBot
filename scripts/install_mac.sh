#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PLIST_NAME="ge.cardarbot.agent.plist"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
PLIST_PATH="${LAUNCH_AGENTS_DIR}/${PLIST_NAME}"

cd "${PROJECT_DIR}"

echo "=== CarDarBot macOS Setup ==="

# 1. Locate Python 3.12+
PYTHON_BIN=""
for candidate in python3.13 python3.12 /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12 python3; do
    if command -v "${candidate}" >/dev/null 2>&1; then
        ver="$("${candidate}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
        major="${ver%%.*}"
        minor="${ver##*.}"
        if [ "${major}" -ge 3 ] && [ "${minor}" -ge 12 ]; then
            PYTHON_BIN="$(command -v "${candidate}")"
            break
        fi
    fi
done

if [ -z "${PYTHON_BIN}" ]; then
    echo "Error: Python 3.12+ is required. Install it via Homebrew: brew install python@3.12"
    exit 1
fi

echo "Using Python interpreter: ${PYTHON_BIN}"

# 2. Create virtual environment and install dependencies
if [ ! -d ".venv" ]; then
    "${PYTHON_BIN}" -m venv .venv
fi
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"

# 3. Prepare directories & .env
mkdir -p data logs
if [ ! -f ".env" ]; then
    cp .env.example .env
    chmod 600 .env
    echo "Created .env from .env.example (permissions 600)."
    echo "IMPORTANT: Edit .env to add your regenerated TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USER_IDS."
fi

# 4. Initialize SQLite database & run Alembic migrations
.venv/bin/alembic upgrade head

chmod +x "${SCRIPT_DIR}/run_bot.sh" "${SCRIPT_DIR}/uninstall_mac.sh"

# 5. Optional launchd installation (Only if --install-launchd flag is explicitly passed)
if [[ "${1:-}" == "--install-launchd" ]]; then
    mkdir -p "${LAUNCH_AGENTS_DIR}"
    cat > "${PLIST_PATH}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>ge.cardarbot.agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PROJECT_DIR}/scripts/run_bot.sh</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>ThrottleInterval</key>
    <integer>30</integer>
    <key>StandardOutPath</key>
    <string>${PROJECT_DIR}/logs/launchd.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${PROJECT_DIR}/logs/launchd.stderr.log</string>
</dict>
</plist>
EOF
    launchctl unload "${PLIST_PATH}" 2>/dev/null || true
    launchctl load "${PLIST_PATH}"
    echo "Installed and loaded launchd agent at: ${PLIST_PATH}"
else
    echo ""
    echo "Setup complete! Background launchd agent was NOT installed automatically."
    echo "To start the bot manually: ./scripts/run_bot.sh"
    echo "To install the macOS launchd background service (after configuring .env): ./scripts/install_mac.sh --install-launchd"
fi
