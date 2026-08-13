#!/usr/bin/env bash
# Idempotently apply Raspberry Pi 4 overclock and governor settings.
set -euo pipefail

ROOT="${ROOT:-$HOME/projects/pi-assistant}"
LOG="$ROOT/logs/setup.log"
UPDATE="$ROOT/update.txt"
CONF="/boot/config.txt"
TS_UTC() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
TS_IST() { TZ=Asia/Kolkata date +"%Y-%m-%d %H:%M:%S %Z"; }
log() { mkdir -p "$ROOT/logs"; printf "%s [oc_apply] %s\n" "$(TS_UTC)" "$1" | tee -a "$LOG"; }
update() { mkdir -p "$(dirname "$UPDATE")"; printf "%s - %s\n" "$(TS_IST)" "$1" >> "$UPDATE"; }

require_root() {
  if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    log "This script needs root; re-running with sudo"
    exec sudo -E bash "$0"
  fi
}

backup_config() {
  mkdir -p "$ROOT/backups"
  local stamp
  stamp="$(date -u +%Y%m%d-%H%M%SZ)"
  cp -a "$CONF" "$ROOT/backups/config.txt.$stamp"
  log "Backed up $CONF to $ROOT/backups/config.txt.$stamp"
}

set_kv() {
  local key="$1" val="$2"
  if grep -qE "^[#[:space:]]*${key}=" "$CONF"; then
    sed -i -E "s|^[#[:space:]]*${key}=.*|${key}=${val}|g" "$CONF"
  else
    printf "%s=%s\n" "$key" "$val" >> "$CONF"
  fi
}

apply_overclock() {
  set_kv arm_freq 2000
  set_kv over_voltage 6
  set_kv gpu_mem 16
  set_kv temp_limit 80
  log "Applied overclock settings to $CONF (arm_freq=2000, over_voltage=6, gpu_mem=16, temp_limit=80)"
}

enable_performance_governor() {
  for f in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    [[ -w "$f" ]] && echo performance > "$f" || true
  done
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -y >/dev/null 2>&1 || true
    apt-get install -y cpufrequtils >/dev/null 2>&1 || true
    echo 'GOVERNOR="performance"' > /etc/default/cpufrequtils
    systemctl enable cpufrequtils >/dev/null 2>&1 || true
    systemctl restart cpufrequtils >/dev/null 2>&1 || true
  fi
  log "Set CPU governor to performance (runtime + cpufrequtils if available)"
}

post_status() {
  if command -v vcgencmd >/dev/null 2>&1; then
    local clk temp thr
    clk="$(vcgencmd measure_clock arm 2>/dev/null || true)"
    temp="$(vcgencmd measure_temp 2>/dev/null || true)"
    thr="$(vcgencmd get_throttled 2>/dev/null || true)"
    log "vcgencmd: $clk | $temp | $thr"
  else
    log "vcgencmd not found; status limited"
  fi
}

main() {
  require_root
  backup_config
  apply_overclock
  enable_performance_governor
  sync
  post_status
  update "Applied overclock and performance governor (arm=2000MHz, ov=6, gpu_mem=16, tlimit=80)."
  log "Overclock apply complete. Reboot required to take full effect."
}
main "$@"
