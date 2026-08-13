# Requirements

One file per service role, not one file for the project.

That is deliberate. These dependencies genuinely conflict: `onnxruntime`,
`ctranslate2` and the Azure Speech SDK cannot share a resolver without pinning
each other into corners, and `visn` runs on a different Python version from the
rest. Each service gets the environment it needs and nothing else, which is why
a vision dependency upgrade cannot break speech.

| File | Environment | Used by |
|---|---|---|
| `base.txt` | all | shared core: pyzmq, pyyaml, pyserial, pytest |
| `stte.txt` | `.venvs/stte` | voice-pipeline — Porcupine, faster-whisper, Azure Speech, webrtcvad |
| `ttse.txt` | `.venvs/ttse` | tts — Azure Speech |
| `llme.txt` | `.venvs/llme` | llm — openai, huggingface-hub |
| `visn.txt` | `.venvs/visn-py313` | vision — onnxruntime, opencv |
| `dise.txt` | `.venvs/dise` | display — pygame |

`base.txt` is not implied. Install it alongside the role file:

```bash
pip install -r requirements/base.txt -r requirements/stte.txt
```

`scripts/recreate_venvs.sh` does this for every environment.

## Notes

`visn.txt` installs **both** `opencv-python` and `opencv-python-headless`,
which provide the same `cv2` module and conflict. It also pins `numpy` twice
with different floors. Neither has broken anything yet; both should be cleaned
up before anyone else builds from this.

`ultralytics` and `torch` are deliberately absent. Nothing at runtime imports
them — `src/vision/detector.py` uses `onnxruntime` only — and `ultralytics` is
AGPL-3.0. Install it in a throwaway environment if you need to export a model,
and keep it out of `.venvs/visn`. See
[models/vision/README.md](../models/vision/README.md).

`azure-cognitiveservices-speech` is a proprietary closed-source binary SDK, and
it is in the default configuration for both STT and TTS. Worth knowing if you
care about the licence story of a build.
