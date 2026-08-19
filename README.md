# Smart Car

A voice-controlled ground robot on a Raspberry Pi 4. You say a wakeword, ask it
something in plain language, and it answers — and if the answer involves moving,
it moves, subject to a safety layer that runs on a separate microcontroller and
can overrule it.

The interesting engineering is not the voice assistant. It is the boundary
between a probabilistic language model and a machine with motors: what happens
when the model is wrong, when the network stalls, when a sensor is unplugged, or
when the computer running all of it stops responding.

---

## Status

**The system works end to end.** Wakeword, speech recognition, language model,
speech synthesis, vision, motion and the Android remote all function together on
the physical robot, and have for some time.

This release is a **hardening layer on top of that working base**. It does not
change what the robot does; it changes how it behaves when something goes wrong.

| | |
|---|---|
| Base system | working on hardware |
| This release — code | complete |
| This release — automated tests | 155 Python, 193 C checks, all passing |
| This release — hardware validation | **in progress, targeted for end of month** |

What the hardening layer adds: watchdogs on every phase that waits on an
external service, a framed link protocol with CRC and a motion deadman,
fail-closed sensor handling, request correlation, an encrypted and
authenticated app channel, and a test suite that covers the protocol and the
safety rules in both languages.

One thing to be explicit about, because the documentation describes it as
though it were live: **the new MCU firmware is built and tested but not yet
flashed.** `src/uart/motor_bridge.py` still speaks the legacy ASCII protocol.
Until both are switched over, the motion lease and fail-closed sensor rules are
not in effect on the robot. That cutover is part of the hardware validation
above.

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

Services never call each other. Everything is a message on a topic, which is
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
they are not what the shipped configuration runs. The default configuration
needs network access and Azure credentials.

### The safety model

The tier that owns physical safety is the least capable one. The Pi runs Linux,
Python, a neural network and three cloud SDKs; it is the component most likely
to hang, crash or get `systemctl stop`ped. So the MCU is the final authority on
motion and the Pi can only ask.

Motion is a **lease, not a latch**: the MCU brakes unless the Pi keeps renewing
it, so an unplugged cable or a crashed orchestrator stops the robot without
depending on the Pi behaving correctly. Sensors fail **closed** — three
simultaneous echo timeouts mean blocked, never clear road.

Wire format and bench checklist: [firmware/PROTOCOL.md](firmware/PROTOCOL.md).

---

## Layout

```
config/        system.yaml — one file, every threshold and engine choice
src/           the Pi services
firmware/      MCU firmware; core/ is portable and unit-tested
requirements/  one file per service role, because the deps conflict
deploy/        systemd units, installer, TLS certificate generation
docker/        dev/CI image and container topology
docs/          architecture, hardware, services, configuration, operations
tools/         debugging utilities
scripts/       build, fetch and setup helpers
mobile_app/    Android remote
book/          project thesis (LaTeX)
```

---

## Running it

The robot runs under systemd. Nine units, one per service:

```bash
cp .env.example .env          # fill it in first — every unit requires it
sudo ./deploy/install.sh --enable
sudo systemctl start orchestrator voice-pipeline llm tts uart
journalctl -fu orchestrator
```

Start the orchestrator first: it binds the message bus, and PUB/SUB drops
anything published before a subscriber has attached.

Four of the nine services also run as containers — see
[docker/README.md](docker/README.md). The two approaches interoperate.

---

## Tests

```bash
docker compose -f docker/compose.yaml run --rm dev
```

Runs the Python suite and the firmware C suite together. This is the easiest
route on Windows, where there is usually no C compiler for the firmware tests.

Natively:

```bash
pip install -r requirements/base.txt
pytest

cmake -S firmware -B firmware/build -G Ninja
cmake --build firmware/build
./firmware/build/sc_tests
```

The link protocol and the motion-safety rules are implemented **twice** — once
in Python (`src/uart/`) and once in C (`firmware/core/`) — and verified against
shared conformance vectors including byte-exact golden frames. If the two ends
of the serial link ever disagree about the wire format, the build fails rather
than the robot.

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

See [firmware/README.md](firmware/README.md) for wiring and the bench bring-up
checklist.

---

## Documentation

Maintained against the source, and they say so where the code disagrees with
the intent.

| Document | What it answers |
|---|---|
| [architecture.md](docs/architecture.md) | How it is built and why. Tiers, IPC rules, state machine, failure modes. |
| [hardware.md](docs/hardware.md) | The actual build. Parts, power design, wiring. |
| [services.md](docs/services.md) | Per-service: what it talks to, how it fails, how to check it. |
| [configuration.md](docs/configuration.md) | Every key in `system.yaml`, including the nineteen read by nothing. |
| [operations.md](docs/operations.md) | Running it, diagnosing it, recovering it. |
| [security.md](docs/security.md) | Threat model and the encrypted app channel. |

Older files under `docs/` predate the current build and are not maintained.
Anything contradicting the six above is wrong.

---

## Licence, attribution, and contributions

Smart Car’s original source and documentation are licensed under the
[Apache License 2.0](LICENSE). The original project copyright is
**Copyright 2026 Kamal Bura**, recorded in [NOTICE](NOTICE). Apache-2.0 lets
you inspect, use, modify, distribute, fork, and contribute to the project,
including for commercial purposes, subject to its notice, attribution, patent,
and redistribution terms. It does not transfer ownership of contributors’ work
to the original author.

Contributions are welcome through forks and pull requests. See
[CONTRIBUTING.md](CONTRIBUTING.md) for contribution, testing, safety, and
attribution expectations. Contributions intentionally submitted for inclusion
are licensed under Apache-2.0; no copyright assignment is required.

### Contributors

- [Himasree Bura](https://github.com/burahimasree)

The Apache licence covers the Smart Car core only. It does not license or claim
ownership of third-party dependencies, cloud services, SDKs, models, firmware,
or assets obtained separately. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
before redistributing a build or developing a commercial product.

Future proprietary hosted services, commercial tooling, hardware designs, or
separately licensed models can be developed independently from the open-source
Apache-2.0 core when the components are genuinely separable and their own terms
are met.

### Known separately licensed runtime components

This project is Apache-2.0 (see [LICENSE](LICENSE)), but the default runtime
configuration pulls in components that are not:

- **Azure Cognitive Services Speech SDK** — proprietary, closed source,
  redistribution restricted. It is the default STT and TTS engine.
- **YOLO11 weights** — AGPL-3.0. No weights are committed; see
  [models/vision/README.md](models/vision/README.md) before building on them.
- **Porcupine keyword files** — licensed per Picovoice account and not
  redistributable. Generate your own:
  [models/wakeword/README.md](models/wakeword/README.md).
