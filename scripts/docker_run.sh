#!/bin/bash
# Manages the mini-obd Docker container on the Pi.
# Sets up slcan0 from a CANable2/SH-C31G adapter before starting the container.
# Uses --network=host so the container sees slcan0 directly.

IMAGE="ghcr.io/toddkimery/mini_obd_build:latest"
CONTAINER="mini-obd"

docker stop "$CONTAINER" 2>/dev/null || true
docker rm   "$CONTAINER" 2>/dev/null || true

# ── Set up SLCAN interface (normaldotcom/canable2 SLCAN firmware) ────────────
setup_can() {
    local TTY
    TTY=$(ls /dev/ttyACM0 /dev/ttyACM1 2>/dev/null | head -1)
    if [ -z "$TTY" ]; then
        echo "[docker_run] No ttyACM device found — adapter not connected"
        return 1
    fi
    echo "[docker_run] Using $TTY"
    sudo pkill -f slcand 2>/dev/null; sleep 0.3
    sudo ip link delete slcan0 2>/dev/null; sleep 0.1
    sudo slcand -o -c -s6 "$TTY" slcan0 && \
        sleep 0.5 && \
        sudo ip link set slcan0 up && \
        sudo ip link set slcan0 txqueuelen 1000 && \
        echo "[docker_run] slcan0 up at 500kbps on $TTY" || \
        echo "[docker_run] slcand failed on $TTY"
}
setup_can

# ── Start container ───────────────────────────────────────────────────────────
exec docker run --name "$CONTAINER" \
    --network=host \
    -v /home/lola/mini_obd/data:/root/mini_obd/data \
    -v /home/lola/mini_obd/logs:/root/mini_obd/logs \
    -v /home/lola/mini_obd/config:/root/mini_obd/config \
    "$IMAGE"
