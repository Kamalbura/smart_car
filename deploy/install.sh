#!/usr/bin/env bash
# Install the systemd units for this checkout.
#
# The unit files hardcode /home/dev/smart_car and User=dev, so a clone anywhere
# else produces nine services that fail on startup with nothing pointing at the
# cause. This rewrites both to match reality before installing.
#
#   sudo ./deploy/install.sh            # install, do not start
#   sudo ./deploy/install.sh --enable   # install and enable at boot
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_SRC="$REPO_ROOT/deploy/systemd"
UNIT_DST=/etc/systemd/system
TEMPLATE_ROOT=/home/dev/smart_car
RUN_USER="${SUDO_USER:-${USER:-root}}"
ENABLE=0

[ "${1:-}" = "--enable" ] && ENABLE=1

if [ "$(id -u)" -ne 0 ]; then
    echo "error: must run as root (use sudo)" >&2
    exit 1
fi

if [ ! -f "$REPO_ROOT/.env" ]; then
    echo "error: $REPO_ROOT/.env is missing." >&2
    echo "       Every unit sets EnvironmentFile to it and will refuse to start." >&2
    echo "       Run: cp .env.example .env  and fill it in." >&2
    exit 1
fi

echo "repo:  $REPO_ROOT"
echo "user:  $RUN_USER"
echo

for unit in "$UNIT_SRC"/*.service; do
    name="$(basename "$unit")"
    # Rewrite paths, and User=dev only -- led-ring.service deliberately runs as
    # root for NeoPixel GPIO timing and must keep it.
    sed -e "s|${TEMPLATE_ROOT}|${REPO_ROOT}|g" \
        -e "s|^User=dev$|User=${RUN_USER}|" \
        "$unit" > "$UNIT_DST/$name"
    echo "installed $name"
done

systemctl daemon-reload
echo
echo "daemon-reload done."

UNITS="orchestrator voice-pipeline llm tts uart vision display led-ring remote-interface"

if [ "$ENABLE" -eq 1 ]; then
    # shellcheck disable=SC2086
    systemctl enable $UNITS
    echo "enabled at boot. Start with: systemctl start $UNITS"
else
    echo "Not enabled. To enable at boot:"
    echo "  sudo systemctl enable $UNITS"
fi

echo
echo "Note: these units set StartLimitIntervalSec=0, which disables systemd's"
echo "restart rate limiter. A service that fails on startup will respawn every"
echo "few seconds indefinitely. Watch: journalctl -fu <name>"
