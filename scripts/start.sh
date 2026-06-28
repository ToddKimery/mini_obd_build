#!/bin/bash
# Generate a self-signed TLS cert on first run, then start uvicorn over HTTPS.
# Chrome Android requires HTTPS (even self-signed) for PWA install + service worker.
set -e

CERT_DIR=/root/mini_obd/config
mkdir -p "$CERT_DIR"

if [ ! -f "$CERT_DIR/cert.pem" ]; then
    echo "[start.sh] Generating self-signed TLS certificate..."
    openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
        -keyout "$CERT_DIR/key.pem" \
        -out  "$CERT_DIR/cert.pem" \
        -subj "/CN=mini-obd" \
        -addext "subjectAltName=IP:192.168.4.1,IP:127.0.0.1,DNS:localhost,DNS:mini-obd.local"
    echo "[start.sh] Certificate written to $CERT_DIR/cert.pem"
fi

echo "[start.sh] Starting uvicorn on https://0.0.0.0:8080"
exec /root/obd_env/bin/uvicorn main:app \
    --host 0.0.0.0 \
    --port 8080 \
    --ssl-keyfile "$CERT_DIR/key.pem" \
    --ssl-certfile "$CERT_DIR/cert.pem"
