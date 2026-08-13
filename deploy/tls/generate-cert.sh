#!/usr/bin/env bash
# Generate a long-lived self-signed certificate for the robot, and print the
# public-key pin the Android app needs.
#
#   ./deploy/tls/generate-cert.sh 100.111.13.60 192.168.1.42
#
# Why self-signed rather than Let's Encrypt: this is a single device talking to
# a single app that you also control. Public CA infrastructure exists to let
# strangers verify strangers, and it costs you a domain name, a reachable port
# 80, and trust in every CA on earth -- any one of which could be coerced into
# issuing a certificate for your name.
#
# Pinning one key you generated yourself is strictly stronger for this case.
# There is no CA to compromise, because there is no CA.
#
# ECDSA P-256 rather than RSA: the handshake signature is far cheaper on a
# Pi 4, which matters when the app reconnects on every network change.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CRT="$HERE/robot.crt"
KEY="$HERE/robot.key"
DAYS=3650

if [ $# -eq 0 ]; then
    echo "usage: $0 <ip-or-hostname> [more...]" >&2
    echo >&2
    echo "Pass every address the app might use to reach the robot: the" >&2
    echo "Tailscale IP, the LAN IP, the mDNS name. A certificate is only" >&2
    echo "valid for the names inside it, and the app will refuse anything" >&2
    echo "not listed." >&2
    exit 1
fi

# Build the SAN list. IP literals and DNS names take different prefixes, and
# getting this wrong produces a certificate that fails validation with a
# thoroughly unhelpful error.
SAN="DNS:smart-car,DNS:smart-car.local,DNS:localhost,IP:127.0.0.1"
for host in "$@"; do
    if [[ "$host" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        SAN="$SAN,IP:$host"
    else
        SAN="$SAN,DNS:$host"
    fi
done

echo "Subject alternative names: $SAN"
echo

openssl req -x509 -nodes \
    -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
    -keyout "$KEY" -out "$CRT" \
    -days "$DAYS" -sha256 \
    -subj "/CN=smart-car" \
    -addext "subjectAltName=$SAN" \
    -addext "keyUsage=critical,digitalSignature,keyEncipherment" \
    -addext "extendedKeyUsage=serverAuth" 2>/dev/null

chmod 600 "$KEY"
chmod 644 "$CRT"

# SPKI hash, base64 — the exact format OkHttp's CertificatePinner expects.
PIN="$(openssl x509 -in "$CRT" -pubkey -noout \
        | openssl pkey -pubin -outform der 2>/dev/null \
        | openssl dgst -sha256 -binary \
        | openssl enc -base64)"

cat <<EOF
Certificate: $CRT
Private key: $KEY   (mode 600 — never commit this)
Valid for:   $DAYS days

Public-key pin for the Android app:

    sha256/$PIN

Put that in the app's Settings screen, or hardcode it in RobotRepository.kt:

    CertificatePinner.Builder()
        .add("100.111.13.60", "sha256/$PIN")
        .build()

The pin covers the public key, not the certificate, so you can reissue the
certificate later with the same key and the app keeps working. Regenerating the
key means updating the app.
EOF
