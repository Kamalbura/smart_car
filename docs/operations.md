# Operations

Running the robot, and what to do when it misbehaves.

## Safety first

Bring the robot up **on blocks, wheels off the ground** after any firmware
change, any wiring change, or any change to `nav.*` or `vision.*` config.

The currently-flashed firmware has **no deadman**. If the Pi dies, the UART
cable comes loose, or you run `systemctl stop uart` while the robot is moving,
it keeps moving. The only thing that stops it is its own <10 cm ultrasonic
check, which is forward-facing only. Until the new firmware is flashed, treat
"the robot is driving" as a state you must end deliberately.

`POST /intent {"intent":"stop"}` is the fastest software stop. Pulling the
drive-pack connector is the fastest real one.

## Starting and stopping

**systemd** (production):

```bash
sudo ./deploy/install.sh --enable        # first time only
sudo systemctl start orchestrator voice-pipeline llm tts uart
sudo systemctl stop uart                 # ⚠ does not stop a moving robot
journalctl -fu orchestrator
```

Start the orchestrator first. It binds the bus; everything else connects to it,
and PUB/SUB drops anything published before a subscriber has attached.

**Docker** (the four containerised services):

```bash
docker compose -f docker/compose.yaml --profile core up -d
docker compose -f docker/compose.yaml logs -f orchestrator
docker compose -f docker/compose.yaml down
```

The two coexist. A containerised orchestrator and a systemd-managed vision
service reach the same bus, provided the systemd ones get `IPC_UPSTREAM` and
`IPC_DOWNSTREAM` pointed at the right address.

## Is it working?

```bash
systemctl status orchestrator voice-pipeline llm tts uart
curl -s http://127.0.0.1:8770/health                        # no token needed
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8770/status | jq
journalctl -fu orchestrator | grep PHASE:
```

A healthy conversation shows `PHASE: IDLE -> LISTENING -> THINKING -> SPEAKING
-> IDLE`. If phases stop appearing, the orchestrator is wedged or is not
hearing the wakeword.

Logs go to both stdout (journald / `docker logs`) and rotating files in
`logs/`. `LOG_LEVEL=DEBUG` raises verbosity without a code change.

## Common failures

**Nothing happens when I say the wakeword.**
Check `voice-pipeline` first. It holds the only microphone handle, and it does
not reopen a device that disappears — it will sit in a retry loop looking
healthy. `systemctl restart voice-pipeline` is the workaround.
Confirm the mic exists: `arecord -l` should list the USB card.

**It hears me but never answers.**
`journalctl -u llm`. Missing Azure credentials produce a clear
`AZURE_OPENAI_API_KEY not configured` and the unit restarts in a loop. If
credentials are fine, the THINKING watchdog releases after 45 s and stops the
motors, so a stuck turn is bounded.

**It answers but says nothing.**
`journalctl -u tts`. A failed synthesis publishes `done: false`, which the
orchestrator discards, so you get a mandatory 60 s stall until the SPEAKING
watchdog fires.

**The app shows "Control offline".**
The remote session expires after 15 s. The app's own poll interval is the
keepalive, so a poll interval above 15000 ms in Settings permanently disables
every control. Check `/status` returns 200 with your token.

**The app connects but all sensor fields are null.**
That was a real bug — `remote_interface` subscribed on `upstream`, where a
connecting SUB receives nothing. Fixed; if you see it again on an older
checkout, that is the cause.

**A service restarts every three seconds forever.**
Eight units set `StartLimitIntervalSec=0`, which disables systemd's rate
limiter. `journalctl -u <name> | head -50` will show the real error at the
first start. The usual cause is a missing `.env`.

**The camera is at 100 % CPU.**
Unplugging the camera mid-run leaves the vision runner spinning on a stale
frame with no sleep. It does not recover. Restart the unit.

## Recovery

**The robot is moving and I want it stopped.**

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json' -d '{"intent":"stop"}' \
     http://127.0.0.1:8770/intent
```

If the orchestrator is the thing that is wedged, that will not work. Stop the
`uart` service and then physically disconnect the drive pack — remember that
stopping `uart` alone does not brake the motors under the current firmware.

**Everything is confused after a crash.**
Restart the orchestrator. All conversation state is in RAM and is meant to be
disposable. Note that it does **not** publish a stop on startup, so stop the
motors first if the robot was moving.

**Vision says it is off but the stream is still running.**
An orchestrator restart resets `vision_mode` to the config default while the
vision runner keeps streaming, and an equality guard suppresses the corrective
message. Toggle vision off and on through the app to resynchronise.

## Routine checks

Before a demo:

1. `systemctl status` on all five core units.
2. Wakeword → LED goes green.
3. One full question and answer.
4. Telemetry present in `/status` — null sensors mean the UART link is down.
5. Battery voltage on both packs. They are separate; either can be flat while
   the other is fine, and a flat drive pack looks exactly like a motor fault.

After any code change:

```bash
docker compose -f docker/compose.yaml run --rm dev
```

After any firmware change, the bench checklist in
[../firmware/README.md](../firmware/README.md) — especially item 7, pulling the
UART cable while driving.
