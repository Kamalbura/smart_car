# Architecture

How the system is put together, why it is put together that way, and where the
design does not yet match the intent.

Everything here is checked against the source. Where the running system differs
from what it should be, that is stated rather than smoothed over — a document
that flatters the code is worse than no document, because people act on it.

---

## 1. What this is

A voice-controlled ground robot. You say a wakeword, ask a question in ordinary
language, and it answers. If the answer involves moving, it moves.

The interesting engineering is not the voice assistant — that is four cloud API
calls in a trench coat. It is the boundary between a probabilistic language
model and a machine with motors: what happens when the model is wrong, when the
network stalls, when a sensor is unplugged, or when the computer running all of
it simply stops responding.

---

## 2. The central decision: three tiers, by trustworthiness

```
┌──────────────────────────────────────────────────────────┐
│ Tier 3   Cloud     Azure Speech, Azure OpenAI            │
│          Smart, slow, unreliable, occasionally wrong     │
└──────────────────────────────────────────────────────────┘
                          ↕  seconds, may fail entirely
┌──────────────────────────────────────────────────────────┐
│ Tier 2   Raspberry Pi 4    orchestration, vision, state  │
│          Capable, complex, can hang or be stopped        │
└──────────────────────────────────────────────────────────┘
                          ↕  milliseconds, over UART
┌──────────────────────────────────────────────────────────┐
│ Tier 1   ESP32     motors, ultrasonics, safety           │
│          Dumb, deterministic, always running             │
└──────────────────────────────────────────────────────────┘
```

Each tier is permitted to fail in a way the tier below can survive.

The rule that falls out of this, and the one that matters most: **the tier that
owns physical safety is the least capable one.** The Pi runs Linux, Python, a
neural network and three cloud SDKs. It is the component most likely to hang,
crash, run out of memory, or get `systemctl stop`ped by its own operator.
Nothing about whether the robot keeps driving into a wall may depend on it
behaving correctly.

So the ESP32 is the final authority on motion. The Pi can only *ask*.

---

## 3. Process topology

Nine systemd units on the Pi (`deploy/systemd/`). Each is a separate OS process
with its own Python environment, so a dependency conflict or a segfault in one
cannot take down another.

| Service | Module | Responsibility |
|---|---|---|
| `orchestrator` | `src.core.orchestrator` | State machine, message router, the only binder |
| `voice-pipeline` | `src.audio.voice_service` | Wakeword + STT in one process, one mic handle |
| `llm` | `src.llm.azure_openai_runner` | Prompt construction, response parsing |
| `tts` | `src.tts.azure_tts_runner` | Speech synthesis and playback |
| `vision` | `src.vision.vision_runner` | Camera, YOLO11n inference, MJPEG encoding |
| `uart` | `src.uart.motor_bridge` | Serial link to the MCU |
| `display` | `src.ui.face_fb` | Face and status, direct framebuffer writes |
| `led-ring` | `src.piled.led_ring_service` | NeoPixel state feedback (runs as root) |
| `remote-interface` | `src.remote.remote_interface` | HTTP API and video stream for the app |

Wakeword and STT deliberately share one process. They both need the microphone,
and on a Pi two processes contending for one ALSA capture device is a source of
intermittent failure that no amount of retry logic fixes properly.

### Dead code you will find in the tree

Several modules look live and are not. `src/audio/unified_voice_pipeline.py`,
`unified_audio.py` and `best_voice_pipeline.py` are superseded by
`voice_service.py`. Both `src/stt/*_runner.py` are unused — STT runs in-process
inside the voice service. `src/llm/gemini_runner.py` and `local_llm_runner.py`
have no unit. `src/uart/bridge.py` is superseded by `motor_bridge.py`.

`config/system.yaml`'s `audio.use_unified_pipeline: true` is read by nothing.
Derive truth from `deploy/systemd/*.service`, never from the config flag.

---

## 4. IPC

Services never call each other. Everything is a message on a ZeroMQ PUB/SUB
topic. That is what lets a service be restarted, containerised or rewritten
without touching its neighbours.

### Two channels, one binder

```
        ┌───────────────────────────────────────────┐
        │            ORCHESTRATOR                   │
        │  SUB bind :6010        PUB bind :6011     │
        └────────▲──────────────────────┬───────────┘
                 │ upstream             │ downstream
                 │ (events)             │ (commands)
     ┌───────────┴────────┐   ┌─────────▼────────────┐
     │ PUB connect        │   │ SUB connect          │
     │ voice, llm, tts,   │   │ every service        │
     │ vision, uart,      │   │                      │
     │ remote-interface   │   │                      │
     └────────────────────┘   └──────────────────────┘
```

The orchestrator **binds both sockets**. Everyone else **connects**. This is
inverted from the textbook example, where the publisher binds, and it has one
consequence that has already cost this project real functionality:

> **A SUB socket that connects to `upstream` receives nothing, ever.**
>
> `upstream` is a bound SUB. A second SUB connecting to it is a SUB-to-SUB
> pairing, which ZMTP refuses. It retries the handshake every few seconds
> forever, reports no error, and delivers zero messages. Measured on libzmq
> 4.3.5: the bound SUB received 18/20, a connecting SUB received 0/20.

This silently disabled the entire world-context feature — every `llm.request`
carried `vision.last_known: null` and `sensors.last_known: null`, so the model
was told the robot could see and sense nothing — and most of the remote
interface's telemetry.

**The rule:** to consume a worker event from another process, add the topic to
the orchestrator's `forwarded` set and subscribe **downstream**. Enforced by
`src/tests/test_ipc_topology.py`, which fails the build if the pattern returns.

### Topics

| Topic | Direction | Rate | Notes |
|---|---|---|---|
| `ww.detected` | voice → orch | event | wakeword fired |
| `stt.transcription` | voice → orch | event | text + confidence |
| `llm.request` / `llm.response` | orch ↔ llm | event | carries `request_id` |
| `tts.speak` | both | event | command down, `started`/`done` up |
| `nav.command` | orch → uart | event | `{direction, reason}` |
| `esp32.raw` | uart → orch | **20 Hz** | telemetry, ~8.5 KB each |
| `visn.object` | vision → orch | 12/s × N | one message *per detection* |
| `visn.frame` | vision → orch → remote | ~12/s | 25–60 KB JPEG |
| `display.state` / `display.text` | orch → ui, led | event | |
| `remote.intent` / `.session` / `.event` | remote ↔ orch | 1 Hz | |
| `system.health` | — | **never** | three subscribers, zero publishers |

Two numbers deserve attention. `esp32.raw` is ~8.5 KB because it re-sends a
50-frame history buffer in **every** message, twenty times a second — 96% of
each message is a replay of the last 2.5 seconds. And `visn.frame` at 25–60 KB
is 400–900× the size of a `nav.command`.

### Priority: there is none, and this is the top structural weakness

`nav.command` and `visn.frame` share the same downstream socket. No priority
classes, no separate control channel, no queue discipline.

At the wire level this is survivable, because ZeroMQ filters by topic at the
publisher, so the UART bridge's pipe carries only `nav.command`. At the *thread*
level it is not: the orchestrator relays every JPEG, re-serialises every 8.5 KB
telemetry frame, and runs the safety FSM **on one thread**. An emergency stop
waits behind whatever that thread is already doing.

No high-water marks are set anywhere, so the libzmq default of 1000 applies.
HWM counts messages, not bytes — 1000 queued JPEGs is roughly 40 MB *per pipe*,
across four pipes in the relay chain. On a Pi, the OOM killer is the real
backpressure mechanism.

**The fix, not yet done:** split the sockets. Control (`nav.command`, `cmd.*`)
on one, bulk (`visn.frame`, `esp32.raw`) on another with `CONFLATE` set so only
the newest frame is ever queued. That removes the entire class of "the stop was
late because of video".

### The slow-joiner problem

ZeroMQ PUB drops messages published before a SUB has finished connecting. There
is no handshake, no retry and no state resync anywhere in this system.

Consequences: the orchestrator's startup LED publish always goes to nobody,
because systemd starts it first. And if the orchestrator restarts while vision
is streaming, its `vision_mode` resets to the config default while the vision
runner keeps streaming — and an equality guard suppresses the corrective
publish, so the two disagree permanently with nothing to reconcile them.

---

## 5. The conversation state machine

`src/core/orchestrator.py`. One explicit phase, one transition table, no
implicit state.

```
        wakeword / manual_trigger
   IDLE ──────────────────────────▶ LISTENING
     ▲                                  │
     │           stt_invalid / stt_timeout
     │◀─────────────────────────────────┤
     │                                  │ stt_valid
     │                                  ▼
     │      llm_no_speech           THINKING
     │◀─────────────────────────────────┤
     │                                  │ llm_with_speech
     │            tts_done              ▼
     │◀───────────────────────────── SPEAKING
     │
     │  any phase ──health_error──▶ ERROR ──error_timeout──▶ IDLE
```

Illegal transitions are refused, not crashed on. Every handler early-returns
when the phase is unexpected.

**Every phase that waits on an external service has a watchdog**, because that
early-return is what makes a missing timeout catastrophic rather than annoying:

| Phase | Timeout | On expiry |
|---|---|---|
| `LISTENING` | `stt.timeout_seconds` | spoken feedback, → IDLE |
| `THINKING` | `llm.timeout_seconds` (45 s) | **stop motors**, feedback, → IDLE |
| `SPEAKING` | `tts.timeout_seconds` (60 s) | **stop motors**, → IDLE |
| `ERROR` | 2 s | → IDLE |

Without the `THINKING` and `SPEAKING` watchdogs, one hung cloud call left the
robot permanently deaf — every subsequent wakeword silently dropped — with the
motors still running from the command issued before the hang.

Responses carry a `request_id`. The orchestrator abandons a turn at 45 s while
the LLM runner has no timeout of its own, so without correlation a very late
reply would be spoken as the answer to a different question, and its `direction`
sent to the motors.

---

## 6. Safety, in two layers

### Layer 1 — the MCU, authoritative

Runs regardless of what the Pi is doing, and may refuse any command.

- **Motion is a lease, not a latch.** Non-zero duty is only maintained while
  valid frames keep arriving. Silence for 300 ms brakes the motors. An
  unplugged cable, a crashed orchestrator and `systemctl stop uart` are all the
  same event from here: silence.
- **Sensors fail closed.** Three simultaneous echo timeouts mean *blocked*,
  never *clear road*.
- **Every direction is gated**, not just forward — but rotation and reverse
  stay available at reduced duty, because a robot that cannot back out of a
  corner is not safe, it is stuck.
- **Clearing a fault re-reads the sensors** before clearing.

### Layer 2 — the Pi, advisory

`motor_bridge` refuses forward when the last telemetry says blocked. This is
defence in depth and nothing more, because it is worthless in the case that
matters most: when the Pi is the thing that failed.

It must still be *correct*. Three fail-open paths — no telemetry ever received,
stale telemetry, and all-sensors-invalid — each used to fall through to
"allowed", so the gate reported a clear road precisely when it knew least. A
check that says "safe" while blind is worse than no check, because it looks
like a safeguard.

### What is actually running

**The deployed MCU stops the robot for obstacles and publishes status telemetry; both behaviours are verified on hardware.**

The robot currently runs `src/uart/esp-code.ino`: newline-delimited ASCII, no
framing, no checksum, latched GPIO. It brakes autonomously below 10 cm, but
only forward is gated, a total sensor failure reads as clear road, and there is
no deadman — if the Pi dies, it keeps driving.

Cutting over needs two changes: flash `firmware/port/esp32`, and switch
`motor_bridge.py` to emit frames via `src/uart/protocol.py`. Until both happen,
the guarantees above are aspirations.

---

## 7. One turn, traced

```
  "hey robo, what do you see?"
        │
        ▼
  voice_service          Porcupine fires          ww.detected ──▶ orch
        │                                          IDLE → LISTENING
        │                                          LED green, mic opens
        ▼
  Azure Speech           transcript + confidence   stt.transcription ──▶ orch
                                                   confidence < 0.3 → reject
        │                                          LISTENING → THINKING
        ▼
  orchestrator           builds request:
                           text, last nav direction,
                           world_context snapshot,
                           request_id                llm.request ──▶ llm
        ▼
  azure_openai_runner    conversation memory +
                         system prompt → Azure
                         tolerant JSON extraction    llm.response ──▶ orch
        │                                            {speak, direction}
        ▼
  orchestrator           obstacle? forward → stop    nav.command ──▶ uart
                                                     tts.speak ──▶ tts
                                                     THINKING → SPEAKING
        ▼
  azure_tts_runner       synthesise, play           tts.speak{done} ──▶ orch
                                                     SPEAKING → IDLE
```

End to end is 3–8 seconds, dominated by the two cloud round trips. Vision runs
independently and asynchronously; the orchestrator requests a capture only when
the transcript suggests one is wanted.

---

## 8. Failure modes

| Event | What happens now |
|---|---|
| Cloud LLM hangs | 45 s watchdog, motors stopped, spoken apology, → IDLE |
| TTS dies mid-utterance | 60 s watchdog, motors stopped, → IDLE |
| Malformed LLM JSON | tolerant extractor returns `{}`, turn degrades to no-speech |
| Non-string `speak` | coerced; previously **killed the orchestrator process** |
| Microphone unplugged | ⚠ voice service loops forever, never reopens, systemd never restarts it |
| Camera unplugged | ⚠ 100% CPU busy-loop, never recovers |
| UART unplugged | Verify after the framed-link migration; the legacy ASCII path does not provide a transport deadman |
| Orchestrator restarts | State lost, phase → IDLE, **no stop published**; motion continues |
| Worker restarts | Transparent reconnect, nobody is notified, messages in the gap are lost |
| Pi loses power | Verify after the framed-link migration; the legacy ASCII path does not provide a transport deadman |

The ⚠ rows are known gaps, not accepted designs.

---

## 9. Deployment

**systemd** is the production path. Nine units, `deploy/install.sh` rewrites the
hardcoded paths for the current checkout. Note that eight units set
`StartLimitIntervalSec=0`, which disables the restart rate limiter — a service
failing at startup respawns every few seconds indefinitely. That is what
produced the `restart counter is at 373` in the committed journals.

**Docker** covers `orchestrator`, `llm`, `remote-interface` and `uart`.
Deliberately excluded: vision (libcamera must version-match the host), voice
(needs the host's ALSA dsnoop devices), led-ring (root + GPIO timing).

The two coexist, because IPC is the same either way. Migrate one service at a
time and stop where the payoff stops.

Containerising `remote-interface` changes its security model: a published port
NATs every request, so the source-IP allowlist sees only the bridge gateway.
`REMOTE_AUTH_TOKEN` is mandatory there.

---

## 10. Testing

| Suite | Count | Needs |
|---|---|---|
| Python unit + integration | 155 | nothing |
| Firmware core (C) | 193 checks | a C compiler |

The protocol and safety rules are implemented twice — Python
(`src/uart/`) and C (`firmware/core/`) — and tested against **shared
conformance vectors**, including byte-exact golden frames. If the two ends of
the serial link ever disagree about the wire format, the build fails rather
than the robot.

`docker compose -f docker/compose.yaml run --rm dev` runs both.

Driver code is not unit-tested. It is verified on the bench against the
checklist in `firmware/README.md`, and the entry that matters is number 7:
pull the UART cable while driving and confirm the wheels stop.

---

## 11. What this architecture does not do yet

**No localisation.** No encoders, no IMU, no odometry. Every motion is
open-loop and unbounded — `duration_ms` is parsed and discarded. "Forward"
means "forward until something else happens". This, not model quality, is why
"go to the kitchen" is unreachable.

**No plan representation.** The LLM emits one direction per turn and the FSM is
per-turn. There is no way to express "I am 3 steps into a 5-step task".

**Vision has no depth.** YOLO gives labels and boxes. Nothing fuses a detection
with the ultrasonic distance, so the robot can say *what* it sees but not
*where* it is.

**Health monitoring is inert.** `system.health` has three subscribers and no
publisher, so the ERROR phase is unreachable via health and the LED's error
branch is dead code.

The dependency order for autonomy is therefore: encoders and an IMU first,
closed-loop distance and turn primitives on the MCU second, a behaviour layer
third, mapping fourth. Adding a better model changes nothing until the robot
knows where it is.

---

## See also

- [hardware.md](hardware.md) — the build, authoritative
- [../firmware/PROTOCOL.md](../firmware/PROTOCOL.md) — wire format, golden vectors
- [../firmware/README.md](../firmware/README.md) — bench bring-up checklist
- [../docker/README.md](../docker/README.md) — container topology
