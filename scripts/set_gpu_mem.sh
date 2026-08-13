#!/usr/bin/env bash
set -euo pipefail
TARGET=${1:-128}
CFG=/boot/firmware/config.txt
BK="${CFG}.$(date +%Y%m%d%H%M%S).bak"
if [ ! -e "$CFG" ]; then
  echo "Config file $CFG not found. Exiting." >&2
  exit 2
fi
if [ ! -w "$CFG" ]; then
  echo "This script needs sudo to modify $CFG. Re-run with sudo." >&2
  exit 3
fi
cp "$CFG" "$BK"
if grep -qi '^gpu_mem=' "$CFG"; then
  sed -i "s/^gpu_mem=.*/gpu_mem=${TARGET}/I" "$CFG"
else
  echo "\n# Ensure sufficient GPU memory for CSI camera" >> "$CFG"
  echo "gpu_mem=${TARGET}" >> "$CFG"
fi
echo "Backed up $CFG -> $BK"
echo "Updated gpu_mem to ${TARGET} in $CFG"
echo "Reboot to apply changes: sudo reboot"
