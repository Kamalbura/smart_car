# App-to-Pi security

The mobile app can request motion. Protecting the app-to-Pi connection is
therefore a safety requirement, not an optional convenience.

## Current implementation

The repository contains the following controls:

| Control | Status |
|---|---|
| Bearer-token authentication | Implemented in `remote-interface` through `REMOTE_AUTH_TOKEN` |
| HTTPS entry point | Implemented through Caddy on port 8443 |
| TLS certificate generation | Provided by `deploy/tls/generate-cert.sh` |
| Certificate pin support | Implemented in the Android app through OkHttp |
| Cleartext HTTP fallback | Still permitted by the Android app; encryption is supported, not enforced |

The Docker deployment exposes Caddy on port 8443 and keeps the Python
`remote-interface` service on the internal Docker network. This means traffic
between the app and Caddy can use TLS, while the local reverse-proxy hop remains
inside that private container network.

## Encryption

The intended transport is TLS 1.3. Caddy and its Go TLS stack select an
appropriate authenticated cipher suite during the handshake. On Raspberry Pi
hardware, that may be `TLS_CHACHA20_POLY1305_SHA256` when ChaCha20-Poly1305 is
the suitable choice. The negotiated suite is a runtime property and must be
verified on the deployed robot.

Do not add a custom ChaCha20-Poly1305 protocol around HTTP requests. TLS already
provides authenticated encryption, key exchange, nonce management, and replay
protection. A custom format would need to solve all of those details correctly.

## Required rollout before claiming an encrypted-only channel

1. Generate the robot certificate and private key with
   `deploy/tls/generate-cert.sh`.
2. Start Caddy and confirm that the app reaches the robot through HTTPS on port
   8443.
3. Configure the Android app to trust the robot certificate and use the printed
   public-key pin.
4. Set a strong `REMOTE_AUTH_TOKEN` in the robot’s untracked `.env` file.
5. Disable cleartext HTTP in the Android network-security configuration and
   remove the user-facing HTTP fallback.
6. Verify that HTTP requests fail, HTTPS requests succeed, and requests without
   the token are rejected.

Until step 5 is complete, the app can be configured to use HTTP. Documentation
must therefore describe encryption as available but not enforced.

## Operational boundaries

- Do not publish `remote-interface` port 8770 directly when Caddy is in use.
- Do not expose the ZeroMQ IPC ports outside the Pi or its private container
  network.
- Treat `REMOTE_AUTH_TOKEN` as a password. Rotate it if a phone is lost or a
  token may have been exposed.
- Certificate pinning supplements certificate validation; it does not replace a
  valid trust chain for a self-signed certificate.
