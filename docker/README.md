# Containers

## Run the tests anywhere

```bash
docker compose -f docker/compose.yaml run --rm dev
```

That runs the Python suite and the firmware C suite in one shot. It is the
fastest way to get the C tests running on Windows, where there is no host
compiler — the image brings its own gcc, cmake and ninja.

## Run the services on the Pi

```bash
docker compose -f docker/compose.yaml --profile runtime up -d
docker compose -f docker/compose.yaml logs -f orchestrator
```

## What is containerised, and why not all of it

Containerised: `orchestrator`, `llm`, `remote-interface`, `uart`. Left on the
host: `vision`, `voice`, `led-ring`, `display`.

The split is not ideological. Those four have either no hardware dependency or
a single device node, so containerising costs nothing. The other four each want
a chunk of the host's hardware stack — libcamera version-matched to the host
kernel, ALSA dsnoop devices defined in `/etc/asound.conf`, GPIO timing that
needs root — and containerising them trades real complexity for very little.

This is safe to do halfway. Services talk over ZeroMQ on host networking, so a
containerised orchestrator and a systemd-managed vision service cannot tell the
difference. Migrate one at a time and stop wherever the payoff stops.

## What this actually buys you

**The venv problem goes away for the services that move.** There are six
virtual environments today because native dependencies conflict;
`setup_envs.sh` creates four of them, in the wrong place, without installing
any requirements; and `systemd/vision.service` and `display.service` reference
a seventh, `.venvs/visn-py313`, that no script creates and no document
mentions. An image per concern is a better answer to that problem than a venv
per concern.

**Restart behaviour gets saner.** Eight of the nine systemd units set
`StartLimitIntervalSec=0`, which disables systemd's start-rate limiter — a unit
that fails on startup respawns every few seconds forever. That is exactly what
`backend-logs/remote_interface_journal_tail.txt` recorded: `restart counter is
at 373`. Docker's `restart: unless-stopped` backs off exponentially instead.

**Memory gets bounded.** Only `voice-pipeline.service` sets a memory limit
today; the other eight are unbounded on a 4 GB Pi. Every container here sets
`mem_limit`.

## What it does not buy you

It does not make the robot more reliable on its own. The things that actually
caused failures — a state machine that wedged with no timeout, motors that kept
running when the Pi died, sensors that read blindness as clear road — are
design bugs. A container would have restarted the process and changed nothing.

It also does not help with cross-architecture builds by itself. Building
`onnxruntime`-class images natively on a Pi 4 is slow; use `docker buildx` with
`--platform linux/arm64` from a development machine and push to a registry when
the heavier services eventually move.

## Containerising `remote-interface` changes its security model

Set `REMOTE_AUTH_TOKEN` before exposing it. This is not optional hardening.

The service's only authentication was a source-IP allowlist
(`remote_interface.allowed_cidrs`). A Docker published port NATs every inbound
connection, so the service sees the bridge gateway — `172.18.0.1` — instead of
the real client. Two things follow:

1. Your existing allowlist rejects everything, including the Android app.
2. "Fixing" that by adding the bridge subnet would make the check meaningless.
   It could no longer distinguish a tailnet peer from any host that reaches
   port 8770 — on an endpoint whose `POST /intent` drives the motors.

IP allowlisting and port publishing are fundamentally incompatible. The token
is checked before the allowlist and is sufficient on its own, because it is the
only control that still means anything behind NAT. Without it the service logs
a warning at startup and falls back to the old behaviour.

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))" >> .env   # edit to REMOTE_AUTH_TOKEN=...
curl -H "Authorization: Bearer $TOKEN" http://pi:8770/health
```

The Android app needs the same header. If you would rather not change the app
yet, run this one service with `network_mode: host` on the Pi so it sees real
client IPs, and keep the allowlist.

## Building for the Raspberry Pi

Images built on an x86-64 machine are `linux/amd64` and will **not** run on a
Pi 4, which is `linux/arm64`. Two options:

**Build on the Pi.** Simplest, no registry needed, and correct by construction:

```bash
docker compose -f docker/compose.yaml build
```

**Cross-build from a development machine.** Faster to iterate, needs somewhere
to put the result:

```bash
docker buildx build --platform linux/arm64 \
    -f docker/Dockerfile.service \
    -t your-registry/smart-car-service:latest --push .
```

Verified working via QEMU emulation on Docker Desktop; check what your buildx
instance supports with `docker buildx inspect --bootstrap`.

Note that the heavier services still on the host — vision especially, with
onnxruntime and OpenCV — would be considerably slower to cross-build. That is
another reason to leave them under systemd for now.

## Caveats

- `network_mode: host` is Linux-only. On Windows and macOS only `dev` works,
  which is fine — the rest need the robot.
- `--profile runtime` requires a populated `.env`. Every service inherits it,
  and a missing file fails the whole profile.
- `uart` needs group access to `/dev/serial0`; `group_add: ["20"]` assumes
  dialout is GID 20, as on Raspberry Pi OS. Verify with `getent group dialout`.
