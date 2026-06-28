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
  echo "[1/4] Building Next.js static export..."
  cd app/web
  npm run build
  cd ../..
  echo "      Output: app/web/out/"
fi

# ── Sync backend ──────────────────────────────────────────────────────────────
if [ "$WEB_ONLY" = false ]; then
  echo "[2/4] Syncing API backend..."
  ssh "$PI_HOST" "mkdir -p $PI_BASE/api"
  rsync -avz --delete \
    --exclude '__pycache__' \
    app/api/ \
    "$PI_HOST:$PI_BASE/api/"

  echo "      Installing/updating Python deps on Pi..."
  ssh "$PI_HOST" "
    /home/lola/obd_env/bin/pip install -q --upgrade \
      fastapi 'uvicorn[standard]' websockets python-multipart aiofiles anthropic
  "
fi

# ── Sync frontend static export ───────────────────────────────────────────────
if [ "$API_ONLY" = false ]; then
  echo "[3/4] Syncing web static export..."
  ssh "$PI_HOST" "mkdir -p $PI_BASE/web/out"
  rsync -avz --delete \
    app/web/out/ \
    "$PI_HOST:$PI_BASE/web/out/"
fi

# ── One-time system config (idempotent) ───────────────────────────────────────
echo "[4/4] Applying system config..."
ssh "$PI_HOST" "
  # Sudoers rule so the service can sync clock from the phone
  SUDOERS=/etc/sudoers.d/mini-obd-time
  if [ ! -f \$SUDOERS ]; then
    echo 'lola ALL=(ALL) NOPASSWD: /usr/bin/timedatectl set-time *' | sudo tee \$SUDOERS > /dev/null
    echo 'lola ALL=(ALL) NOPASSWD: /bin/date -s *' | sudo tee -a \$SUDOERS > /dev/null
    sudo chmod 0440 \$SUDOERS
    echo '      Clock-sync sudoers rule added.'
  else
    echo '      Clock-sync sudoers rule already present.'
  fi

  # Install + enable systemd service
  sudo cp $PI_BASE/api/mini_obd_api.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable mini_obd_api
  sudo systemctl restart mini_obd_api
  sleep 2
  systemctl is-active mini_obd_api && echo '      Service: running' || echo '      Service: FAILED — check: journalctl -u mini_obd_api -n 50'
"

echo ""
echo "==> Deploy complete."
echo "    App:      http://mini-obd.local:8080"
echo "    Via AP:   http://192.168.4.1:8080"
echo ""
echo "    Add your Anthropic API key via the gear icon in the app."
