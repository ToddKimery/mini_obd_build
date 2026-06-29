#!/bin/bash
# Manages the mini-obd Docker container on the Pi.
# Sets up slcan0 from a CANable2/SH-C31G adapter before starting the container.
# Uses --network=host so the container sees slcan0 directly.

IMAGE="ghcr.io/toddkimery/mini_obd_build:latest"
CONTAINER="mini-obd"

docker stop "$CONTAINER" 2>/dev/null || true
docker rm   "$CONTAINER" 2>/dev/null || true

# ── Set up SLCAN interface ────────────────────────────────────────────────────
setup_slcan() {
    local tty=""
    for dev in /dev/ttyACM0 /dev/ttyACM1 /dev/ttyUSB0 /dev/ttyUSB1; do
        [ -e "$dev" ] && tty="$dev" && break
    done
    [ -z "$tty" ] && echo "[docker_run] No CAN adapter found — slcan0 not set up" && return 0

    # Tear down any stale interface
    sudo ip link set slcan0 down 2>/dev/null || true
    sudo pkill -f "slcand.*$tty" 2>/dev/null || true
    sleep 0.3

    echo "[docker_run] Starting slcand on $tty -> slcan0 (500kbps)"
    sudo slcand -o -c -s6 "$tty" slcan0 2>/dev/null && \
        sudo ip link set slcan0 up && \
        echo "[docker_run] slcan0 up" || \
        echo "[docker_run] slcan0 setup failed (adapter may not be ready)"
}
setup_slcan

# ── Start container ───────────────────────────────────────────────────────────
exec docker run --name "$CONTAINER" \
    --network=host \
    -v /home/lola/mini_obd/data:/root/mini_obd/data \
    -v /home/lola/mini_obd/logs:/root/mini_obd/logs \
    -v /home/lola/mini_obd/config:/root/mini_obd/config \
    "$IMAGE"
