#!/usr/bin/env bash
# Builds the Next.js frontend and deploys everything to the Pi.
# Run from mini_obd_build/
# Usage: bash app/deploy.sh [--web-only | --api-only]
set -e

PI_HOST="lola@mini-obd.local"
PI_BASE="/home/lola/mini_obd/app"

WEB_ONLY=false
API_ONLY=false
for arg in "$@"; do
  case $arg in
    --web-only) WEB_ONLY=true ;;
    --api-only) API_ONLY=true ;;
  esac
done

echo "==> Mini OBD Deploy"
echo "    Target: $PI_HOST:$PI_BASE"
echo ""

# ── Build Next.js ─────────────────────────────────────────────────────────────
if [ "$API_ONLY" = false ]; then
  echo "[1/3] Building Next.js static export..."
  cd app/web
  npm run build
  cd ../..
  echo "      Output: app/web/out/"
fi

# ── Sync backend ──────────────────────────────────────────────────────────────
if [ "$WEB_ONLY" = false ]; then
  echo "[2/3] Syncing API backend..."
  ssh "$PI_HOST" "mkdir -p $PI_BASE/api"
  rsync -avz --delete \
    --exclude '__pycache__' \
    app/api/ \
    "$PI_HOST:$PI_BASE/api/"

  echo "      Installing/updating Python deps on Pi..."
  ssh "$PI_HOST" "
    /home/lola/obd_env/bin/pip install -q --upgrade \
      fastapi uvicorn[standard] websockets python-multipart aiofiles
  "
fi

# ── Sync frontend static export ───────────────────────────────────────────────
if [ "$API_ONLY" = false ]; then
  echo "[3/3] Syncing web static export..."
  ssh "$PI_HOST" "mkdir -p $PI_BASE/web/out"
  rsync -avz --delete \
    app/web/out/ \
    "$PI_HOST:$PI_BASE/web/out/"
fi

# ── Install + restart systemd service ────────────────────────────────────────
echo ""
echo "==> Restarting mini_obd_api service..."
ssh "$PI_HOST" "
  sudo cp $PI_BASE/api/mini_obd_api.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable mini_obd_api
  sudo systemctl restart mini_obd_api
  sleep 1
  systemctl is-active mini_obd_api && echo 'Service: running' || echo 'Service: FAILED'
"

echo ""
echo "==> Done. Open http://mini-obd.local in Chrome"
echo "    Or via AP: http://192.168.4.1"
