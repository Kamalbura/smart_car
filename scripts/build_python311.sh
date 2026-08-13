#!/usr/bin/env bash
# Build and install Python 3.11.x from source (altinstall under /usr/local).
set -euo pipefail

PY_VER="${PY_VER:-3.11.9}"
URL_BASE="https://www.python.org/ftp/python/${PY_VER}"
TARBALL="Python-${PY_VER}.tar.xz"
ROOT="${ROOT:-$HOME/projects/pi-assistant}"
WORK="${WORK:-/tmp/python-build-${PY_VER}}"
PREFIX="/usr/local"
LOG="$ROOT/logs/setup.log"
UPDATE="$ROOT/update.txt"

TS_UTC() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
TS_IST() { TZ=Asia/Kolkata date +"%Y-%m-%d %H:%M:%S %Z"; }
log() { mkdir -p "$ROOT/logs"; printf "%s [py311] %s\n" "$(TS_UTC)" "$1" | tee -a "$LOG"; }
update() { mkdir -p "$(dirname "$UPDATE")"; printf "%s - %s\n" "$(TS_IST)" "$1" >> "$UPDATE"; }

require_root() {
  if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    log "This step needs root; re-running with sudo"
    exec sudo -E PY_VER="$PY_VER" ROOT="$ROOT" WORK="$WORK" bash "$0"
  fi
}

install_deps() {
  apt-get update -y
  DEPS=(build-essential libssl-dev zlib1g-dev libncurses5-dev libncursesw5-dev libreadline-dev
        libsqlite3-dev libgdbm-dev libgdbm-compat-dev libbz2-dev libffi-dev liblzma-dev
        tk-dev uuid-dev wget curl ca-certificates xz-utils)
  apt-get install -y "${DEPS[@]}"
  log "Build dependencies installed."
}

fetch_and_verify() {
  mkdir -p "$WORK" && cd "$WORK"
  if [[ ! -f "$TARBALL" ]]; then
    curl -fSLo "$TARBALL" "${URL_BASE}/${TARBALL}"
    log "Downloaded $TARBALL"
  else
    log "Tarball already present (skip download)"
  fi
  if curl -fSL "${URL_BASE}/${TARBALL}.sha256" -o "${TARBALL}.sha256" 2>/dev/null; then
    sha256sum --check "${TARBALL}.sha256"
    log "SHA256 verified using official .sha256 file."
  else
    HASH="$(sha256sum "$TARBALL" | awk '{print $1}')"
    log "NOTE: Unable to fetch official .sha256; computed SHA256=$HASH (please cross-check)."
  fi
}

build_install() {
  tar -xf "$TARBALL"
  cd "Python-${PY_VER}"
  ./configure --prefix="$PREFIX" --enable-optimizations --with-lto --enable-shared
  make -j"$(nproc)"
  make altinstall
  echo "$PREFIX/lib" >/etc/ld.so.conf.d/python${PY_VER%.*}.conf
  ldconfig
  log "Python ${PY_VER} installed via altinstall."
  "$PREFIX/bin/python${PY_VER%.*}" -m ensurepip --upgrade || true
  "$PREFIX/bin/python${PY_VER%.*}" -m pip install --upgrade pip setuptools wheel
  log "pip/setuptools/wheel upgraded for Python ${PY_VER%.*}"
}

post_smoke() {
  "$PREFIX/bin/python${PY_VER%.*}" -V | tee -a "$LOG"
  "$PREFIX/bin/python${PY_VER%.*}" - <<'PY'
import sys, ssl, sqlite3
print("OK: py", sys.version.split()[0], "ssl", ssl.OPENSSL_VERSION.split()[1], "sqlite", sqlite3.sqlite_version)
PY
  log "Python ${PY_VER%.*} smoke tests complete."
}

main() {
  require_root
  install_deps
  fetch_and_verify
  build_install
  post_smoke
  update "Built and installed Python ${PY_VER} from source (altinstall)."
}
main "$@"
