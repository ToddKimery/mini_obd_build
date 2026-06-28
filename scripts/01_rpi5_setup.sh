#!/bin/bash
# ============================================================
# Mini Cooper R56 N14 - RPi5 Setup Script (Docker deployment)
# Verified for: Raspberry Pi 5, Ubuntu 24.04 LTS (arm64)
#               WD Black SN7100 2TB NVMe via USB enclosure
# Usage: chmod +x 01_rpi5_setup.sh && sudo ./01_rpi5_setup.sh
# ============================================================

set -e

echo "================================================"
echo " Mini R56 N14 OBD Logger - RPi5 Docker Setup"
echo "================================================"

ACTUAL_USER="${SUDO_USER:-$(logname 2>/dev/null || echo ubuntu)}"
USER_HOME="/home/${ACTUAL_USER}"
IMAGE="ghcr.io/toddkimery/mini_obd_build:latest"

echo "  User: ${ACTUAL_USER}  Home: ${USER_HOME}"

# ── Step 1: System update (minimal — avoid heavy write spikes) ─
echo ""
echo "[1/6] Updating system..."
apt-get update -q

# snapd causes apt upgrade failures on RPi5 (snap store unreachable)
DEBIAN_FRONTEND=noninteractive apt-get remove --purge snapd -y 2>/dev/null || true
rm -rf /snap /var/snap /var/lib/snapd /var/cache/snapd /root/snap 2>/dev/null || true

# Upgrade only security-critical packages, not the full dist
DEBIAN_FRONTEND=noninteractive apt-get install -y --only-upgrade \
    openssl libssl3 libssl-dev 2>/dev/null || true

# ── Step 2: Minimal dependencies ──────────────────────────────
echo "[2/6] Installing dependencies..."
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    git \
    curl \
    ca-certificates \
    gnupg \
    usbutils \
    can-utils \
    udev \
    nano \
    htop \
    net-tools \
    network-manager \
    cpufrequtils

# ── Step 3: Install Docker ─────────────────────────────────────
echo "[3/6] Installing Docker..."
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update -q
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    docker-ce docker-ce-cli containerd.io docker-buildx-plugin

systemctl enable docker
systemctl start docker
usermod -aG docker "${ACTUAL_USER}"
echo "  ✓ Docker installed"

# ── Step 4: Project directories + udev rules ──────────────────
echo "[4/6] Creating project structure and udev rules..."
mkdir -p "${USER_HOME}/mini_obd/logs" \
         "${USER_HOME}/mini_obd/data" \
         "${USER_HOME}/mini_obd/config"
chown -R "${ACTUAL_USER}:${ACTUAL_USER}" "${USER_HOME}/mini_obd"

# K+DCAN FT232RL udev rules
cat > /etc/udev/rules.d/99-mini-obd.rules << 'EOF'
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", \
    SYMLINK+="kdcan", MODE="0666", GROUP="dialout"
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6010", \
    SYMLINK+="kdcan", MODE="0666", GROUP="dialout"
EOF
udevadm control --reload-rules && udevadm trigger
usermod -aG dialout "${ACTUAL_USER}"
echo "  ✓ udev rules installed"

# ── Step 5: Pull image + create systemd service ───────────────
echo "[5/6] Pulling Docker image from GHCR..."
sudo -u "${ACTUAL_USER}" docker pull "${IMAGE}" || {
    echo "  ⚠ Pull failed — image may be private. Run after logging in:"
    echo "    docker login ghcr.io -u ToddKimery"
    echo "    docker pull ${IMAGE}"
}

cat > /etc/systemd/system/mini_obd.service << EOF
[Unit]
Description=Mini R56 N14 OBD Docker Container
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=simple
User=${ACTUAL_USER}
Restart=on-failure
RestartSec=10
ExecStartPre=-/usr/bin/docker stop mini-obd
ExecStartPre=-/usr/bin/docker rm mini-obd
ExecStart=/usr/bin/docker run --name mini-obd --rm \
    -p 8080:8080 \
    --device-cgroup-rule='c 188:* rmw' \
    -v /dev:/dev \
    -v ${USER_HOME}/mini_obd/data:/root/mini_obd/data \
    -v ${USER_HOME}/mini_obd/logs:/root/mini_obd/logs \
    -v ${USER_HOME}/mini_obd/config:/root/mini_obd/config \
    ${IMAGE}
ExecStop=/usr/bin/docker stop mini-obd

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable mini_obd
systemctl start mini_obd
echo "  ✓ Service started"

# ── Step 6: Auto-update timer ─────────────────────────────────
echo "[6/6] Setting up auto-update timer..."
cp "${USER_HOME}/mini_obd/scripts/mini_obd_update.service" /etc/systemd/system/
cp "${USER_HOME}/mini_obd/scripts/mini_obd_update.timer"   /etc/systemd/system/
systemctl daemon-reload
systemctl enable mini_obd_update.timer
systemctl start  mini_obd_update.timer
echo "  ✓ Auto-update timer enabled"

# Sudoers for clock sync
cat > /etc/sudoers.d/mini-obd-time << EOF
${ACTUAL_USER} ALL=(ALL) NOPASSWD: /usr/bin/timedatectl set-time *
${ACTUAL_USER} ALL=(ALL) NOPASSWD: /bin/date -s *
EOF
chmod 0440 /etc/sudoers.d/mini-obd-time

echo ""
echo "================================================"
echo " Setup Complete!"
echo "================================================"
echo ""
echo "  App will be at: http://$(hostname -I | awk '{print $1}'):8080"
echo ""
echo "  Next: plug in OBD adapter and open the app"
echo ""
