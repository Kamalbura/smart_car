#!/usr/bin/env bash
set -euo pipefail

ROOT="${PROJECT_ROOT:-/home/dev/project_root}"
VENV="$ROOT/.venvs/stte"
LOG="$ROOT/logs/setup.log"
UPDATE="$ROOT/update.txt"
WW_DIR="$ROOT/models/wakeword"
# Default access key path; can be overridden by env or .env in project root
ACCESS_KEY_FILE="${ACCESS_KEY_FILE:-$HOME/.config/pi-assistant/pv_access_key}"
# Default public repo for porcupine keyword files (may not be valid for all targets)
PICO_URL="${PICO_URL:-https://raw.githubusercontent.com/Picovoice/porcupine/master/resources/keyword_files/raspberry-pi}"

log() { mkdir -p "$ROOT/logs"; printf "%s %s\n" "$(date -u +%FT%TZ)" "$1" | tee -a "$LOG"; }
ist_now() { TZ=Asia/Kolkata date +"%Y-%m-%d %H:%M:%S %Z"; }
update() { mkdir -p "$(dirname "$UPDATE")"; printf "%s - %s\n" "$(ist_now)" "$1" >> "$UPDATE"; }

echo "[setup] Wakeword setup starting" | tee -a "$LOG"
mkdir -p "$WW_DIR"

# If a project-local .env exists, load it (exports variables)
ENV_FILE="$ROOT/.env"
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -o allexport
  # shellcheck disable=SC1091
  source "$ENV_FILE"
  set +o allexport
  log "Loaded environment variables from $ENV_FILE"
fi

# Activate venv
if [[ ! -d "$VENV" ]]; then
  echo "[setup] Creating venv $VENV" | tee -a "$LOG"
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install --upgrade pip

# Try installing pvporcupine==3.0.5; fallback to torch if unavailable
if pip install --quiet pvporcupine==3.0.5; then
  log "Installed pvporcupine==3.0.5"
else
  log "pvporcupine unavailable; installing torch for fallback"
  if python -c "import torch; print('ok')" 2>/dev/null | grep -q ok; then
    log "PyTorch already present"
  else
    pip install --quiet torch --index-url https://download.pytorch.org/whl/cpu || pip install --quiet torch
    log "PyTorch installed"
  fi
fi

mkdir -p "$WW_DIR"

# If an access key file exists (or ACCESS_KEY was provided), try to fetch .ppn files
if [[ -n "${ACCESS_KEY:-}" ]] || [[ -f "$ACCESS_KEY_FILE" ]]; then
  # If ACCESS_KEY not set but file exists, read it
  if [[ -z "${ACCESS_KEY:-}" ]] && [[ -f "$ACCESS_KEY_FILE" ]]; then
    ACCESS_KEY="$(cat "$ACCESS_KEY_FILE")"
  fi

  if [[ -n "${PICO_URL:-}" ]]; then
    log "Using keyword repo: $PICO_URL"
    declare -a KW_NAMES=("hey-pico.ppn" "picovoice.ppn" "blueberry.ppn" "terminator.ppn" "ok-google.ppn" "hey-google.ppn" "computer.ppn")
    for fname in "${KW_NAMES[@]}"; do
      target="$WW_DIR/${fname}"
      if [[ -f "$target" ]]; then
        log "Keyword $fname already downloaded at $target"
        continue
      fi
      url="$PICO_URL/$fname"
      log "Attempting to fetch $url"
      if curl -fL -o "$target" "$url" >/dev/null 2>&1; then
        sha=$(sha256sum "$target" | awk '{print $1}')
        log "Downloaded keyword $fname -> $target (sha256=$sha)"
      else
        log "Attempt download failed for $url; trying space variant"
        spaced_name="${fname//-/ }"
        url2="$PICO_URL/$spaced_name"
        if curl -fL -o "$target" "$url2" >/dev/null 2>&1; then
          sha=$(sha256sum "$target" | awk '{print $1}')
          log "Downloaded keyword $spaced_name -> $target (sha256=$sha)"
        else
          log "Failed to download $fname or $spaced_name; leaving placeholder"
          rm -f "$target" || true
        fi
      fi
    done

    # Attempt to download custom PPNs (requires ACCESS_KEY for private endpoints)
    log "Attempting to download porcupine ppn variants from $PICO_URL"
    for variant in genny "hey genny" "hi genny" genie jeni; do
      sanitized=${variant// /_}
      target="$WW_DIR/${sanitized}.ppn"
      if [[ -f "$target" ]]; then
        log "PPN for $variant already exists at $target"
        continue
      fi
      url="$PICO_URL/${sanitized}.ppn"
      if [[ -n "${ACCESS_KEY:-}" ]]; then
        if curl -fL -H "Authorization: ${ACCESS_KEY}" -o "$target" "$url" >/dev/null 2>&1; then
          log "Downloaded $variant to $target"
          sha=$(sha256sum "$target" | awk '{print $1}')
          log "SHA256($target)=$sha"
        else
          log "Failed to download $variant from $url"
          rm -f "$target" || true
        fi
      else
        log "Skipping private PPN $variant because ACCESS_KEY not provided"
      fi
    done
  else
    log "No PICO_URL provided; skipping auto-download. Provide PICO_URL env to fetch .ppn files."
  fi
else
  log "No Picovoice access key found or ACCESS_KEY env not set; falling back to energy-based listener / PyTorch fallback"
fi

deactivate || true
update "Setup wakeword: porcupine installed or fallback prepared."
log "Wakeword setup complete"

echo "Done"
