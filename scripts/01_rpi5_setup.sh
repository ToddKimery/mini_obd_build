#!/bin/bash
# ============================================================
# Mini Cooper R56 N14 - RPi5 OBD Logger Setup Script
# Verified for: Raspberry Pi 5, Ubuntu 24.04 LTS (arm64)
#               WD Black SN7100 2TB NVMe via USB-C
# Usage: chmod +x 01_rpi5_setup.sh && sudo ./01_rpi5_setup.sh
# ============================================================

set -e

echo "================================================"
echo " Mini R56 N14 OBD Logger - RPi5 Ubuntu Setup"
echo "================================================"

# ── Detect actual username (not root) ───────────────────────
# Ubuntu 24.04 on RPi5 uses the username you set in Imager
# NOT "pi" like Raspberry Pi OS
ACTUAL_USER="${SUDO_USER:-$(logname 2>/dev/null || echo ubuntu)}"
USER_HOME="/home/${ACTUAL_USER}"
echo "  Detected user: ${ACTUAL_USER}"
echo "  Home dir:      ${USER_HOME}"

# ── Verify we're on Ubuntu 24.04 arm64 ──────────────────────
echo ""
echo "[PRE-CHECK] Verifying system..."
lsb_release -a 2>/dev/null || true
uname -m  # Should print aarch64
echo ""

# ── Step 1: System Update ────────────────────────────────────
echo "[1/8] Updating system packages..."
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get upgrade -y

# ── Step 2: Core Dependencies ────────────────────────────────
echo "[2/8] Installing core dependencies..."
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3-pip \
    python3-venv \
    python3-dev \
    python3-full \
    git \
    sqlite3 \
    screen \
    usbutils \
    can-utils \
    bluetooth \
    bluez \
    libffi-dev \
    libssl-dev \
    libglib2.0-dev \
    pkg-config \
    build-essential \
    udev \
    curl \
    wget \
    htop \
    nano \
    net-tools \
    wireless-tools \
    network-manager \
    nmtui \
    cpufrequtils

# ── NOTE: python3-bluez is NOT available on Ubuntu 24.04 ─────
# It was replaced - bleak pip package handles BLE instead
# DO NOT apt install python3-bluez on Ubuntu 24.04

# ── Step 3: NVMe Storage Setup ───────────────────────────────
echo "[3/8] Checking NVMe storage..."
echo "  Block devices:"
lsblk
echo ""
df -h
echo ""

# Create OBD data partition directory on NVMe
# Ubuntu mounts NVMe root at / - all data goes under /home
mkdir -p "${USER_HOME}/mini_obd/logs"
mkdir -p "${USER_HOME}/mini_obd/data"
mkdir -p "${USER_HOME}/mini_obd/models"
mkdir -p "${USER_HOME}/mini_obd/config"
mkdir -p "${USER_HOME}/mini_obd/scripts"
chown -R "${ACTUAL_USER}:${ACTUAL_USER}" "${USER_HOME}/mini_obd"
echo "  Project structure created at ${USER_HOME}/mini_obd/"

# ── Step 4: Python Virtual Environment ───────────────────────
echo "[4/8] Creating Python virtual environment..."

# Ubuntu 24.04 requires --system-site-packages OR explicit venv
# Using isolated venv (recommended)
sudo -u "${ACTUAL_USER}" python3 -m venv "${USER_HOME}/obd_env" \
    --prompt "obd_env"

# Activate for this script session
source "${USER_HOME}/obd_env/bin/activate"

# ── Step 5: Python Packages ───────────────────────────────────
echo "[5/8] Installing Python packages..."
pip install --upgrade pip setuptools wheel

# OBD-II core
pip install python-obd      # ELM327/K+DCAN OBD-II library
pip install pyserial        # Serial port support for K+DCAN USB

# CAN bus (future CANable 2.0 / SN65HVD230 expansion)
pip install python-can
pip install cantools

# BLE (future Veepeak BLE expansion)
# bleak replaces python-bluez on Ubuntu 24.04
pip install bleak

# Data logging & analysis
pip install pandas
pip install numpy
pip install matplotlib
pip install scikit-learn

# Verify critical packages
echo ""
echo "  Verifying package installation..."
python3 -c "
import obd, serial, can, pandas, numpy, sklearn, bleak
print('  ✓ All packages installed successfully')
print(f'  ✓ python-obd version: {obd.__version__}')
print(f'  ✓ pyserial version: {serial.__version__}')
print(f'  ✓ pandas version: {pandas.__version__}')
" || echo "  ⚠ Some packages may have issues - check output above"

deactivate

# Fix ownership of venv
chown -R "${ACTUAL_USER}:${ACTUAL_USER}" "${USER_HOME}/obd_env"

# ── Step 6: K+DCAN udev Rules ────────────────────────────────
echo "[6/8] Configuring udev rules for K+DCAN..."

# FT232RL vendor:product IDs
# 0403:6001 = Standard FT232RL (most K+DCAN cables)
# 0403:6010 = FT2232 (some variants)
cat > /etc/udev/rules.d/99-mini-obd.rules << 'EOF'
# K+DCAN FT232RL - maps to /dev/kdcan
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", \
    SYMLINK+="kdcan", MODE="0666", GROUP="dialout"

# K+DCAN FT2232 variant
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6010", \
    SYMLINK+="kdcan", MODE="0666", GROUP="dialout"

# CANable 2.0 Pro / SN65HVD230 (future expansion)
SUBSYSTEM=="tty", ATTRS{idVendor}=="16d0", ATTRS{idProduct}=="117e", \
    SYMLINK+="canable", MODE="0666", GROUP="dialout"

# CANable USB alternative ID
SUBSYSTEM=="tty", ATTRS{idVendor}=="1d50", ATTRS{idProduct}=="606f", \
    SYMLINK+="canable", MODE="0666", GROUP="dialout"
EOF

udevadm control --reload-rules
udevadm trigger

# ── Step 7: Add user to dialout group ────────────────────────
echo "[7/8] Adding ${ACTUAL_USER} to dialout group..."
# dialout group = serial port access on Ubuntu (NOT pi group like RPi OS)
usermod -aG dialout "${ACTUAL_USER}"
usermod -aG bluetooth "${ACTUAL_USER}"
echo "  ✓ Added to dialout and bluetooth groups"
echo "  ⚠ Logout/login required for group changes to take effect"

# ── Step 8: Performance & Boot Config ────────────────────────
echo "[8/8] Optimising RPi5 for headless server use..."

# Set CPU to performance mode (better for consistent logging)
echo performance | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
echo 'GOVERNOR="performance"' > /etc/default/cpufrequtils

# Create systemd service (disabled until tested)
cat > /etc/systemd/system/mini_obd.service << EOF
[Unit]
Description=Mini R56 N14 OBD Data Logger
After=network.target
# Wait for USB devices to be ready
After=dev-kdcan.device
Wants=dev-kdcan.device

[Service]
Type=simple
User=${ACTUAL_USER}
WorkingDirectory=${USER_HOME}/mini_obd
ExecStart=${USER_HOME}/obd_env/bin/python ${USER_HOME}/mini_obd/scripts/03_obd_logger.py
Restart=on-failure
RestartSec=30
# Restart up to 5 times then give up
StartLimitBurst=5
StartLimitIntervalSec=300

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
echo "  Service created (disabled - enable after testing)"

# ── Final Summary ─────────────────────────────────────────────
echo ""
echo "================================================"
echo " Setup Complete!"
echo "================================================"
echo ""
echo "  User         : ${ACTUAL_USER}"
echo "  Project dir  : ${USER_HOME}/mini_obd/"
echo "  Python env   : ${USER_HOME}/obd_env/"
echo "  udev rules   : /etc/udev/rules.d/99-mini-obd.rules"
echo ""
echo "  IMPORTANT: Log out and back in for group"
echo "  membership (dialout) to take effect"
echo ""
echo "  Next steps:"
echo "  1. Log out and back in"
echo "  2. Plug K+DCAN into RPi5 USB port"
echo "  3. Check: ls -la /dev/kdcan"
echo "  4. Activate env: source ~/obd_env/bin/activate"
echo "  5. Test: python ~/mini_obd/scripts/02_test_connection.py"
echo ""
