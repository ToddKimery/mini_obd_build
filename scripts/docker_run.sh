#!/bin/bash
# Manages the mini-obd Docker container on the Pi.
# Sets up slcan0 from a CANable2/SH-C31G adapter before starting the container.
# Uses --network=host so the container sees slcan0 directly.

IMAGE="ghcr.io/toddkimery/mini_obd_build:latest"
CONTAINER="mini-obd"

docker stop "$CONTAINER" 2>/dev/null || true
docker rm   "$CONTAINER" 2>/dev/null || true

# ── Set up gs_usb CAN interface (candleLight firmware) ───────────────────────
setup_can() {
    if ip link show can0 &>/dev/null; then
        sudo ip link set can0 up type can bitrate 500000 2>/dev/null && \
            echo "[docker_run] can0 up at 500kbps" || \
            echo "[docker_run] can0 already up or failed"
    else
        echo "[docker_run] No can0 interface found — adapter may not be connected"
    fi
}
setup_can

# ── Start container ───────────────────────────────────────────────────────────
# obd_manager.py override: lets us update the file on Pi without rebuilding the image
OBD_MGR_OVERRIDE=""
[ -f /home/lola/mini_obd/config/obd_manager.py ] && \
    OBD_MGR_OVERRIDE="-v /home/lola/mini_obd/config/obd_manager.py:/root/mini_obd/app/api/obd_manager.py:ro"

exec docker run --name "$CONTAINER" \
    --network=host \
    $OBD_MGR_OVERRIDE \
    -v /home/lola/mini_obd/data:/root/mini_obd/data \
    -v /home/lola/mini_obd/logs:/root/mini_obd/logs \
    -v /home/lola/mini_obd/config:/root/mini_obd/config \
    "$IMAGE"
