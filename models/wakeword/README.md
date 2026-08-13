# Wakeword model

The Porcupine keyword file (`hey_robo.ppn`) is **not** committed, and must not
be. Picovoice keyword files are generated per-account and their terms do not
permit redistribution — a `.ppn` from someone else's console is not yours to
ship, and the same applies to the AccessKey that loads it.

Generate your own. It takes about two minutes and the free tier is enough.

## 1. Get an AccessKey

Sign up at <https://console.picovoice.ai>, copy your AccessKey, and put it in
your untracked `.env`:

```
PV_ACCESS_KEY=your-key-here
```

`config/system.yaml` reads it via `${ENV:PV_ACCESS_KEY}`. Never paste a key into
`.env.example`, `config/system.yaml`, or any tracked file.

## 2. Train a keyword

In the console, go to **Porcupine → Train Wake Word**:

- Phrase: `hey robo` (or whatever you want — see the note below)
- Platform: **Raspberry Pi** — the `.ppn` is platform-specific, and a Linux or
  Windows build will fail to load on the Pi
- Download the `.ppn` and save it as:

```
models/wakeword/hey_robo.ppn
```

If you choose a different phrase, update all three of these in
`config/system.yaml` so they agree:

```yaml
wakeword:
  payload_keyword: "hey robo"
  keywords:
    - hey robo
  model: ${PROJECT_ROOT}/models/wakeword/hey_robo.ppn
```

## 3. Phrase selection actually matters

Detection quality depends far more on the phrase than on the sensitivity knob.
Pick something that is:

- **three or more syllables** — short phrases false-trigger constantly
- **not a common English fragment** — "hey robo" is good, "okay go" is not
- **phonetically distinct from your own speech patterns**

`wakeword.sensitivity` (default `0.75`) trades false accepts against false
rejects. Raise it if the robot ignores you; lower it if it wakes up to the
television.

## 4. Verify

```bash
python -m src.audio.voice_service --config config/system.yaml
```

Watch for the model to load without an error, then say the phrase. On success
the orchestrator logs `PHASE: IDLE -> LISTENING (event: wakeword)` and the LED
ring flashes green.

Note that the wakeword engine runs **inside** `src/audio/voice_service.py`, not
as its own process — it shares one microphone handle with STT to avoid ALSA
contention on the Pi. There is no separate `src/wakeword/` package; older docs
that reference one are describing a layout that no longer exists.
