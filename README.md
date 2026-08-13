# Smart Car

A voice-controlled ground robot on a Raspberry Pi 4. You say a wakeword, ask it
something in plain language, and it answers — and if the answer involves moving,
it moves, subject to a safety layer that runs on a separate microcontroller and
can overrule it.

The interesting engineering is not the voice assistant. It is the boundary
between a probabilistic language model and a machine with motors: what happens
when the model is wrong, when the network stalls, when a sensor is unplugged,
or when the Pi stops responding entirely.

---

## How it works

```
 wakeword ──▶ STT ──▶ LLM ──▶ TTS ──▶ speaker
                       │
                       └──▶ nav.command ──▶ UART ──▶ MCU ──▶ motors
                                                      ▲
                                   ultrasonics ───────┘  (may refuse)
```

Eight Python services on the Pi, coordinated by a phase-based state machine,
talking over ZeroMQ PUB/SUB on localhost. One microcontroller on the other end
of a serial line owning the motors.

Services do not call each other. Everything is a message on a topic, which is
what lets a service be restarted, containerised or replaced without touching
its neighbours.

### Engines

| Role | Implementation |
|---|---|
| Wakeword | Porcupine, in-process with STT |
| Speech-to-text | Azure Speech (cloud) |
| Language model | Azure OpenAI (cloud) |
| Text-to-speech | Azure Speech (cloud) |
| Vision | YOLO11n via ONNX Runtime, on-device |
| Motion + sensing | ESP32, own firmware |

Local alternatives exist in the tree — faster-whisper, llama.cpp, Piper — but
they are **not** what the shipped configuration runs. Set `stt.engine`,
`llm.engine` and the matching systemd unit if you want them. Note that the
default configuration therefore needs network access and Azure credentials;
this is not currently an offline-first system, whatever earlier documentation
claimed.

### The safety model — built and tested, not yet flashed

Read this section as a migration in progress, because two firmwares exist for
one MCU and only the older one is live.

**Running today** (`src/uart/esp-code.ino` + `src/uart/motor_bridge.py`):
newline-delimited ASCII, no framing or checksum, and motor state is latched
GPIO. If the Pi dies or the cable comes loose, the robot keeps driving. The
MCU does brake autonomously below 10 cm, but only forward is gated and a total
sensor failure reads as clear road.

**Built, unit-tested, and ready** (`firmware/` + `src/uart/protocol.py` +
`src/uart/safety.py`): a framed CRC protocol where motion is a **lease, not a
latch** — the MCU brakes within 300 ms unless the Pi keeps renewing it, so an
unplugged cable, a crashed orchestrator or `systemctl stop uart` all stop the
robot without depending on the Pi behaving correctly. Sensors fail **closed**,
every direction is gated, and rotation and reverse stay available at reduced
speed so the robot can back out of a corner.

Cutting over needs two things: flash `firmware/port/esp32`, and change
`motor_bridge.py` to emit frames via `src/uart/protocol.py` instead of ASCII
tokens. Until both happen, the guarantees above are not in effect on the robot.

Wire format and bench checklist: [firmware/PROTOCOL.md](firmware/PROTOCOL.md).

---

## Documentation

Start with these three. They are maintained against the source and say so when
the code disagrees with the intent.

| Document | What it answers |
|---|---|
| **[docs/architecture.md](docs/architecture.md)** | How it is built and why. Tiers, IPC rules, the state machine, failure modes, what is not true yet. |
| **[docs/hardware.md](docs/hardware.md)** | The actual build. Parts, power design, wiring, and corrections to everything else in the repo. |
| **[firmware/PROTOCOL.md](firmware/PROTOCOL.md)** | The Pi ↔ MCU wire contract, with byte-exact golden vectors. |

Then, as needed: [firmware/README.md](firmware/README.md) for bench bring-up,
[docker/README.md](docker/README.md) for containers, and the numbered
`docs/0*.md` set for per-service reference.

A warning about the older material: `docs/08_embedded_esp32_layer.md` and
`docs/05_services_reference.md` describe a **different robot** — a pin map that
contradicts the firmware on every line, an OLED that does not exist, a
16-LED ring on the wrong GPIO. They predate the current build. Trust
`docs/hardware.md` and the source.

## Layout

```
config/      system.yaml — one file, every threshold and engine choice
src/         the Pi services
firmware/    MCU firmware; core/ is portable and unit-tested
deploy/      systemd units, host config, installer
docker/      dev/CI image and container topology
docs/        architecture, hardware, per-service reference
tools/       one-off debugging utilities
scripts/     build, fetch and setup helpers
mobile_app/  Android remote
book/        project thesis (LaTeX)
```

---

## Running it

The robot runs under systemd. Nine units, one per service:

```bash
sudo cp deploy/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now orchestrator voice-pipeline llm tts uart
journalctl -fu orchestrator
```

Each unit requires `/home/dev/smart_car/.env`. A missing `.env` fails every
service with no obvious diagnostic, so create it first:

```bash
cp .env.example .env   # then fill it in
```

Alternatively, run the software services in containers — see
[docker/README.md](docker/README.md). The two approaches interoperate, because
IPC is host-network ZeroMQ either way.

---

## Tests

```bash
docker compose -f docker/compose.yaml run --rm dev
```

Runs the Python suite and the firmware C suite together. This is the easiest
route on Windows, where there is usually no C compiler for the firmware tests.

Natively:

```bash
pip install -r requirements.txt
pytest                                       # Python

cmake -S firmware -B firmware/build -G Ninja # firmware core
cmake --build firmware/build
./firmware/build/sc_tests
```

The firmware's protocol and safety logic are tested twice — once in Python
(`src/uart/`) and once in C (`firmware/core/`) — against shared conformance
vectors, so the two ends of the serial link cannot silently disagree.

---

## Firmware

```bash
cd firmware/port/esp32
idf.py set-target esp32
idf.py build
idf.py -p COM5 flash monitor
```

Requires ESP-IDF v5.2. `idf.py` must run from a real ESP-IDF shell — under Git
Bash it prints `MSys/Mingw is no longer supported` **and exits 0 without
building anything**, so check that `build/smart_car_mcu.bin` exists rather than
trusting the exit code.

See [firmware/README.md](firmware/README.md) for wiring, the bench bring-up
checklist, and notes on the planned STM32/HK32 port.

---

## Third-party licensing

This project is Apache-2.0 (see [LICENSE](LICENSE)), but the default runtime
configuration pulls in components that are not:

- **Azure Cognitive Services Speech SDK** — proprietary, closed source,
  redistribution restricted. It is the default STT and TTS engine.
- **YOLO11 weights** — AGPL-3.0. No weights are committed; see
  [models/vision/README.md](models/vision/README.md) for the obligations before
  you build anything on them.
- **Porcupine keyword files** — licensed per Picovoice account and not
  redistributable. Generate your own:
  [models/wakeword/README.md](models/wakeword/README.md).

---

## Status

Working: the full voice loop, vision detection, remote control from the Android
app, and the motion-safety layer.

Known gaps, honestly:

- `system.health` has three subscribers and no publisher, so health-driven
  behaviour is inert.
- The audio service does not reopen a microphone that disappears, and its
  cloud STT call has no timeout.
- `scripts/run.sh` refers to modules that no longer exist; systemd is the only
  supported way to start the stack.
- Vision is `off` by default and must be enabled per session.
- There is no rear sensor, so reverse is blind and permanently speed-capped.
