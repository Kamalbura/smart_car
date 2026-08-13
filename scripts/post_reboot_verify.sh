#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-$HOME/projects/pi-assistant}"
LOG="$ROOT/logs/setup.log"
TS_UTC() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log() { mkdir -p "$ROOT/logs"; printf "%s [verify] %s\n" "$(TS_UTC)" "$1" | tee -a "$LOG"; }

ok=true
if command -v vcgencmd >/dev/null 2>&1; then
  CLK="$(vcgencmd measure_clock arm | awk -F= '{print $2}' 2>/dev/null || echo 0)"
  TEMP="$(vcgencmd measure_temp 2>/dev/null || echo temp=unknown)"
  THR="$(vcgencmd get_throttled 2>/dev/null || echo throttled=unknown)"
  log "Clock(Hz)=$CLK | $TEMP | $THR"
  if [[ "$CLK" -lt 1800000000 ]]; then
    log "WARN: ARM clock < 1.8GHz (expected ~2.0GHz under load)"; ok=false
  fi
else
  log "vcgencmd not available. Skipping clock/temp checks."
fi

GOV_FILE="/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"
if [[ -r "$GOV_FILE" ]]; then
  GOV="$(cat "$GOV_FILE")"
  log "Governor=$GOV"
  [[ "$GOV" == "performance" ]] || { log "WARN: Governor not performance"; ok=false; }
else
  log "Governor file not readable."
fi

$ok && { log "POST-REBOOT VERIFY: OK"; exit 0; } || { log "POST-REBOOT VERIFY: ATTENTION NEEDED"; exit 1; }
