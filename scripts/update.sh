#!/bin/bash
# Pull latest image from GHCR and restart the container.
# Runs automatically via mini_obd_update.timer (every 30 min when online)
# or manually:  bash ~/mini_obd/scripts/update.sh

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

IMAGE="ghcr.io/toddkimery/mini_obd_build:latest"
CONTAINER="mini-obd"
LOG="$HOME/mini_obd/logs/update.log"
mkdir -p "$HOME/mini_obd/logs"

FORCE=false
for arg in "$@"; do
    case $arg in --force) FORCE=true ;; esac
done

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

# ── Internet check ─────────────────────────────────────────────
if ! /usr/bin/curl -sf --max-time 8 https://ghcr.io > /dev/null 2>&1; then
    log "No internet — skipping update"
    exit 0
fi

log "=== mini-obd update started${FORCE:+ (forced)} ==="

# ── Pull latest image ──────────────────────────────────────────
OLD_ID=$(docker inspect --format='{{.Id}}' "$IMAGE" 2>/dev/null || echo "none")
log "Pulling $IMAGE ..."
docker pull "$IMAGE" 2>&1 | tee -a "$LOG"
NEW_ID=$(docker inspect --format='{{.Id}}' "$IMAGE" 2>/dev/null || echo "unknown")

if [ "$OLD_ID" = "$NEW_ID" ] && [ "$FORCE" = false ]; then
    log "Already up to date"
    log "=== Done ==="
    exit 0
fi

log "Image updated — restarting container..."

# ── Restart container ──────────────────────────────────────────
docker stop "$CONTAINER" 2>/dev/null || true
docker rm   "$CONTAINER" 2>/dev/null || true

# Find OBD device — try known paths
OBD_DEVICE=""
for dev in /dev/kdcan /dev/ttyUSB0 /dev/ttyUSB1 /dev/ttyACM0; do
    [ -e "$dev" ] && OBD_DEVICE="--device $dev:$dev" && break
done

docker run -d \
    --name "$CONTAINER" \
    --restart unless-stopped \
    -p 8080:8080 \
    $OBD_DEVICE \
    -v "$HOME/mini_obd/data:/root/mini_obd/data" \
    -v "$HOME/mini_obd/logs:/root/mini_obd/logs" \
    -v "$HOME/mini_obd/config:/root/mini_obd/config" \
    "$IMAGE" 2>&1 | tee -a "$LOG"

log "=== Update complete ==="
