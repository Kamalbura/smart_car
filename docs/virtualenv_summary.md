# Virtual Environment Summary

| Environment | Location | Key Packages | Intended Use |
|-------------|----------|--------------|--------------|
| `tenv` | `/home/dev/tenv` | `adafruit-blinka`, `adafruit-circuitpython-neopixel`, `rpi_ws281x`, `RPi.GPIO`, `pyserial` | Standalone hardware experiments outside the repo (LED ring quick tests, GPIO bring-up). |
| `.venv` | `/home/dev/project_root/.venv` | Core stack: `pvporcupine`, `PyAudio`, `onnxruntime`, `opencv-python`, `pyserial`, NeoPixel deps | Main development/runtime env for orchestrator and most services. |
| `.venv_test` | `/home/dev/project_root/.venv_test` | `pytest`, `numpy`, `opencv-python` | Lightweight test-only env for CI or fast unit tests. |
| `.venvs/core` | `/home/dev/project_root/.venvs/core` | `pygame`, `pyserial`, `pyzmq`, `PyYAML` | Core control/UI/IPC utilities without heavy ML deps. |
| `.venvs/dise` | `/home/dev/project_root/.venvs/dise` | NeoPixel/GPIO stack plus `pygame`, `evdev`, `pillow`, `python-dotenv`, `yt-dlp` | General display/device helpers (legacy display runner, AnyDesk/display scripts). |
| `.venvs/llme` | `/home/dev/project_root/.venvs/llme` | `huggingface_hub`, `httpx`, `typer`, `numpy` | Large language model orchestration (model downloads, CLI tooling). |
| `.venvs/stte` | `/home/dev/project_root/.venvs/stte` | `faster-whisper`, `ctranslate2`, `torch`, `pvporcupine`, `webrtcvad`, Azure SDK | Speech-to-text & wakeword processing. |
| `.venvs/ttse` | `/home/dev/project_root/.venvs/ttse` | `piper-tts`, `onnxruntime`, `numpy` | Text-to-speech synthesis service. |
| `.venvs/visn` | `/home/dev/project_root/.venvs/visn` | `torch`, `torchvision`, `ultralytics`, `onnx`, `opencv`, NeoPixel deps | Vision/object-detection plus the new LED ring service (shared NeoPixel/RPi GPIO stack). |

**Recommendation for LED ring work:** use `.venvs/visn` (same stack as the LED service + vision models) so the hardware driver matches the orchestrator-facing implementation.
