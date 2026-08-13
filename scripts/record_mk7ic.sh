#!/bin/bash
set -e

OUT=mk7ic.wav
DURATION=${1:-5}
SAMPLE_RATE=16000
CHANNELS=1
FORMAT=S16_LE

echo "Checking arecord for capture devices..."
if ! command -v arecord >/dev/null; then
  echo "arecord not found. Please install alsa-utils and try again." >&2
  exit 2
fi

CAPTURE_LIST=$(arecord -l 2>/dev/null)
if echo "$CAPTURE_LIST" | grep -q "^\*\*\*\*"; then
  echo "No capture devices found."
  echo "Run 'dmesg | tail -n 40' after plugging your USB mic, or run 'sudo udevadm monitor --udev --kernel' while plugging it in." 
  exit 3
fi

# Parse first capture card/device
CARD_LINE=$(echo "$CAPTURE_LIST" | grep -m1 "card [0-9]" || true)
if [ -z "$CARD_LINE" ]; then
  echo "No capture card lines found in 'arecord -l' output." >&2
  echo "$CAPTURE_LIST"
  exit 4
fi

# Example card line: "card 1: Device [USB Audio Device], device 0: USB Audio [USB Audio]"
CARD_NUM=$(echo "$CARD_LINE" | sed -n 's/.*card \([0-9]\+\):.*/\1/p')
DEV_NUM=$(echo "$CAPTURE_LIST" | awk -v card="$CARD_NUM" '/card/ {c=$0} /device/ && NR>0 { if (index(c, "card " card ":") ) { print $0; exit }}' | sed -n 's/.*device \([0-9]\+\):.*/\1/p')

if [ -z "$DEV_NUM" ]; then
  # fallback: default to device 0
  DEV_NUM=0
fi

DEVICE_STR="plughw:${CARD_NUM},${DEV_NUM}"

echo "Recording ${DURATION}s to ${OUT} from ${DEVICE_STR} (rate ${SAMPLE_RATE})"
arecord -D "$DEVICE_STR" -f "$FORMAT" -c $CHANNELS -r $SAMPLE_RATE -d $DURATION "$OUT"
RC=$?
if [ $RC -ne 0 ]; then
  echo "Recording failed with exit $RC" >&2
  exit $RC
fi

echo "Recording completed: $OUT"
ls -lh "$OUT"
exit 0
