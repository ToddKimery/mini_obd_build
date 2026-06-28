#!/bin/bash
# Pull latest code from GitHub and rebuild/restart mini-obd.
# Runs automatically via mini_obd_update.timer (every 30 min when online)
# or manually:  bash ~/mini_obd/scripts/update.sh

REPO_DIR="/home/lola/mini_obd"
LOG="$REPO_DIR/logs/update.log"
mkdir -p "$REPO_DIR/logs"

FORCE=false
for arg in "$@"; do
    case $arg in --force) FORCE=true ;; esac
done

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

# ── Internet check ────────────────────────────────────────────────────────────
if ! curl -sf --max-time 8 https://api.github.com > /dev/null 2>&1; then
    log "No internet — skipping update"
    exit 0
fi

log "=== mini-obd update started${FORCE:+ (forced)} ==="
cd "$REPO_DIR"

# ── Git pull ──────────────────────────────────────────────────────────────────
OLD=$(git rev-parse HEAD 2>/dev/null || echo "none")
git pull --ff-only origin main 2>&1 | tee -a "$LOG"
NEW=$(git rev-parse HEAD)

if [ "$OLD" = "$NEW" ] && [ "$FORCE" = false ]; then
    log "Already up to date ($NEW)"
    log "=== Done ==="
    exit 0
fi

[ "$OLD" != "$NEW" ] && log "Updated $OLD → $NEW"

# ── Rebuild frontend ──────────────────────────────────────────────────────────
WEB_CHANGED=$(git diff --name-only "$OLD" "$NEW" 2>/dev/null | grep -c "^app/web/" || true)
if [ "$FORCE" = true ] || [ "$WEB_CHANGED" -gt 0 ]; then
    log "Rebuilding frontend..."
    cd "$REPO_DIR/app/web"
    npm install --prefer-offline --silent
    npm run build 2>&1 | tee -a "$LOG"
    log "Frontend rebuilt"
    cd "$REPO_DIR"
fi

# ── Update Python deps ────────────────────────────────────────────────────────
REQS_CHANGED=$(git diff --name-only "$OLD" "$NEW" 2>/dev/null | grep -c "requirements.txt" || true)
if [ "$FORCE" = true ] || [ "$REQS_CHANGED" -gt 0 ]; then
    log "Updating Python deps..."
    /home/lola/obd_env/bin/pip install -q -r "$REPO_DIR/app/api/requirements.txt"
    log "Python deps updated"
fi

# ── Restart service ───────────────────────────────────────────────────────────
log "Restarting service..."
sudo systemctl restart mini_obd_api
log "=== Update complete ($NEW) ==="
