# Securing the app channel

The robot's HTTP interface can drive the motors. Everything below follows from
that one fact.

## Threat model

Two questions, often confused, with different answers:

1. **Can someone read or alter the traffic?** — encryption.
2. **Is this person allowed to command the motors?** — authorisation.

The project had an answer to neither for a while. It had a source-IP allowlist,
which is a weak proxy for the second and no answer at all to the first.

## The three paths in

| Path | Encryption | Authorisation |
|---|---|---|
| Over Tailscale | WireGuard — ChaCha20-Poly1305, Curve25519, auto rekey | bearer token |
| LAN, no Tailscale | TLS 1.3 via Caddy | bearer token |
| Public internet | TLS 1.3 via Caddy | bearer token |

**If you use Tailscale, the channel is already encrypted with ChaCha20-Poly1305
and always has been** — that is WireGuard's AEAD. Tailscale also traverses NAT
and carrier-grade NAT, so "external networks" is already solved: install the
Tailscale client on the phone and it works from mobile data, a café, anywhere.

TLS exists for the cases Tailscale does not cover: someone on the LAN who has
not joined the tailnet, or exposing the robot deliberately.

## Why ChaCha20-Poly1305 here

The Pi 4's Cortex-A72 has **no ARMv8 crypto extensions** — Broadcom left them
out of the BCM2711. `/proc/cpuinfo` shows `fp asimd evtstrm crc32 cpuid`, with
no `aes`, no `pmull`, no `sha2`. So AES-GCM runs entirely in software there,
while ChaCha20 is built from ADD/ROT/XOR precisely for that situation. Expect
roughly 2–3× the throughput for the same power, and it is constant-time by
construction, so it also avoids the cache-timing exposure that table-driven
software AES carries.

You do not have to configure this. Go's `crypto/tls` detects at runtime whether
the CPU has AES hardware and prefers ChaCha20-Poly1305 when it does not, so
Caddy on a Pi negotiates `TLS_CHACHA20_POLY1305_SHA256` on its own. Go does not
allow TLS 1.3 cipher suites to be set by hand, which here is a feature: the
automatic choice is already the correct one.

**Do not implement ChaCha20-Poly1305 yourself.** Its 96-bit nonce must never
repeat under one key. Reuse does not degrade it — it leaks the XOR of the
plaintexts *and* the Poly1305 key, so an attacker can forge messages. A robot
that reboots and restarts a counter at zero reuses nonces immediately. TLS
handles this; hand-rolled framing routinely does not.

## Setting it up

**1. Generate a certificate.** Pass every address the app might use:

```bash
./deploy/tls/generate-cert.sh 100.111.13.60 192.168.1.42
```

It prints a pin like `sha256/kkWfzty7...=`. A certificate is only valid for the
names inside it, so an address you forget here is an address the app will
refuse.

**2. Set a token.** In the robot's `.env`:

```bash
python -c "import secrets; print('REMOTE_AUTH_TOKEN=' + secrets.token_urlsafe(32))" >> .env
```

**3. Start the stack.**

```bash
docker compose -f docker/compose.yaml --profile core up -d
```

Caddy listens on 8443. `remote-interface` is no longer published to the host at
all — the only way in is through TLS.

**4. Trust the certificate in the app.** OkHttp's `CertificatePinner` does
**not** replace chain validation, it adds to it, so a self-signed certificate is
rejected by the default trust manager before the pin is ever consulted. Copy the
certificate in and uncomment the trust anchor:

```bash
cp deploy/tls/robot.crt mobile_app/app/src/main/res/raw/robot.crt
# then uncomment <certificates src="@raw/robot" /> in
# mobile_app/app/src/main/res/xml/network_security_config.xml
```

**5. Enter the token and pin** in the app's Settings screen, set the port to
8443, and leave the HTTPS switch on.

## Why pinning rather than a public CA

This app talks to exactly one device that you own. Public CA infrastructure
exists so strangers can verify strangers; using it here would cost a domain
name, a reachable port 80, and trust in every CA Android ships — any one of
which could be induced to issue a certificate for your name.

Pinning one key you generated yourself is strictly stronger for this case.
There is no CA to compromise because there is no CA. The pin covers the public
key rather than the certificate, so you can reissue the certificate on the same
key without touching the app.

## What is still not protected

**The `dev` and `hardware` profiles.** Only `remote-interface` is behind TLS.
The ZeroMQ bus has no authentication or encryption of any kind — anything that
can reach ports 6010/6011 can publish `nav.command` directly. On a single host
that is contained by Docker's network isolation; do not expose those ports.

**`/health` is deliberately unauthenticated.** It returns only "this process is
up", it is needed by container orchestration, and an open port already reveals
that much. Every other route requires the token.

**Replay.** TLS prevents replay on the wire. Nothing above the transport gives
`POST /intent` a nonce or timestamp, so an attacker who obtains a valid token
can repeat a captured command. The token is the boundary; treat it like a
password and rotate it if a phone is lost.

**Rate limiting.** There is none. A client with a valid token can issue
commands as fast as it likes.

**The token is stored in Android SharedPreferences**, which is private to the
app but readable on a rooted device.
