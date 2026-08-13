#!/usr/bin/env bash
# Run every suite that does not need hardware.
#
# Exits non-zero if either the Python or the C side fails, so this works
# unchanged as a CI entrypoint.
set -uo pipefail

cd /workspace
status=0

echo "=============================================="
echo " Python suite"
echo "=============================================="
python -m pytest src/tests -q || status=1

echo
echo "=============================================="
echo " Firmware core (C)"
echo "=============================================="
cmake -S firmware -B firmware/build-docker -G Ninja >/dev/null || status=1
cmake --build firmware/build-docker >/dev/null || status=1
./firmware/build-docker/sc_tests || status=1

echo
if [ "$status" -eq 0 ]; then
    echo "ALL SUITES PASSED"
else
    echo "FAILURES PRESENT (see above)"
fi
exit "$status"
