#!/usr/bin/env bash
set -euo pipefail

PLIST_NAME="ge.cardarbot.agent.plist"
PLIST_PATH="${HOME}/Library/LaunchAgents/${PLIST_NAME}"

echo "=== Uninstalling CarDarBot macOS launchd Service ==="

if [ -f "${PLIST_PATH}" ]; then
    launchctl unload "${PLIST_PATH}" 2>/dev/null || true
    rm -f "${PLIST_PATH}"
    echo "Removed launchd agent: ${PLIST_PATH}"
else
    echo "No launchd plist found at ${PLIST_PATH}."
fi

echo "Done. Local database (data/cardarbot.db) and .env were preserved."
