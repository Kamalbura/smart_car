#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

declare -a ENVS=(stte ttse llme visn)

for env_name in "${ENVS[@]}"; do
    if [[ -d "${PROJECT_ROOT}/${env_name}" ]]; then
        echo "[skip] ${env_name} already exists"
        continue
    fi
    echo "[create] ${env_name}"
    python3 -m venv "${PROJECT_ROOT}/${env_name}"
    source "${PROJECT_ROOT}/${env_name}/bin/activate"
    python -m pip install --upgrade pip setuptools wheel >/dev/null
    deactivate
    echo "[ready] ${env_name}"
done

echo "All virtual environments are prepared."
