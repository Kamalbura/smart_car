#!/bin/bash
cd /home/dev/smart_car
source .venvs/stte/bin/activate
set -a
source .env
set +a
echo Starting e2e test...
timeout 60 python tools/e2e_voice_test.py
