#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-$HOME/projects/pi-assistant}"
LOG="$ROOT/logs/setup.log"
UPDATE="$ROOT/update.txt"
TS_UTC() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
TS_IST() { TZ=Asia/Kolkata date +"%Y-%m-%d %H:%M:%S %Z"; }
log() { mkdir -p "$ROOT/logs"; printf "%s [reboot] %s\n" "$(TS_UTC)" "$1" | tee -a "$LOG"; }
update() { printf "%s - %s\n" "$(TS_IST)" "$1" >> "$UPDATE"; }

echo "Overclock changes are prepared. Reboot is required."
read -r -p "Proceed to reboot now? [y/N]: " ans
if [[ "${ans,,}" == "y" ]]; then
  log "User confirmed reboot. Syncing and rebooting..."
  update "User-triggered reboot to apply overclock."
  sudo sync || true
  sudo systemctl reboot || sudo reboot || true
else
  log "User skipped reboot for now."
fi
