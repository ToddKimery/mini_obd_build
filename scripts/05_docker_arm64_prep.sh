#!/bin/bash
# ============================================================
# Mini Cooper R56 N14 - Docker ARM64 Build Prep
# Run this ON YOUR LAPTOP (Xaos-Ubuntu) tonight
# Builds and tests the full OBD environment in an ARM64
# container so everything is ready to deploy to RPi5 tomorrow
#
# Prerequisites:
#   - Docker installed on Xaos-Ubuntu
#   - Scripts 01-04 downloaded into ~/mini_obd_build/scripts/
#
# Usage:
#   chmod +x 05_docker_arm64_prep.sh
#   ./05_docker_arm64_prep.sh
# ============================================================

set -e

BUILD_DIR="${HOME}/Desktop/Code/mini_obd_build"
SCRIPTS_DIR="${BUILD_DIR}/scripts"

echo "================================================"
echo " Mini R56 N14 - Docker ARM64 Environment Prep"
echo " Running on: $(uname -m) host → building arm64"
echo "================================================"
echo ""

# ── Step 1: Check Docker ──────────────────────────────────────
echo "[1/6] Checking Docker..."
if ! command -v docker &>/dev/null; then
    echo "  Docker not found. Installing..."
    sudo apt-get update
    sudo apt-get install -y docker.io
    sudo systemctl start docker
    sudo systemctl enable docker
    sudo usermod -aG docker "${USER}"
    echo ""
    echo "  ⚠  Added you to docker group."
    echo "  ⚠  You need to log out and back in, then re-run this script."
    echo "  ⚠  Or run: newgrp docker"
    exit 0
else
    echo "  ✓ Docker $(docker --version | cut -d' ' -f3 | tr -d ',')"
fi

# Check docker daemon is running
if ! docker info &>/dev/null; then
    echo "  Docker daemon not running. Starting..."
    sudo systemctl start docker
fi

# ── Step 2: Enable ARM64 emulation ───────────────────────────
echo ""
echo "[2/6] Enabling ARM64 (aarch64) emulation via QEMU..."
docker run --privileged --rm tonistiigi/binfmt --install arm64
echo ""

# Verify arm64 emulation works
echo "  Verifying arm64 emulation..."
ARCH=$(docker run --rm --platform linux/arm64 \
    ubuntu:24.04 uname -m 2>/dev/null)

if [ "${ARCH}" = "aarch64" ]; then
    echo "  ✓ ARM64 emulation working (got: ${ARCH})"
else
    echo "  ✗ ARM64 emulation failed (got: ${ARCH})"
    exit 1
fi

# ── Step 3: Create project directory ─────────────────────────
echo ""
echo "[3/6] Setting up build directory..."
mkdir -p "${SCRIPTS_DIR}"
mkdir -p "${BUILD_DIR}/mini_obd/logs"
mkdir -p "${BUILD_DIR}/mini_obd/data"
mkdir -p "${BUILD_DIR}/mini_obd/models"
mkdir -p "${BUILD_DIR}/mini_obd/config"
mkdir -p "${BUILD_DIR}/mini_obd/scripts"
echo "  ✓ Build dir: ${BUILD_DIR}"

# Check scripts exist
echo ""
echo "  Checking for OBD scripts..."
MISSING=0
for f in 01_rpi5_setup.sh 02_test_connection.py \
          03_obd_logger.py 04_analyse.py; do
    if [ -f "${SCRIPTS_DIR}/${f}" ]; then
        echo "  ✓ ${f}"
    else
        echo "  ✗ ${f} — NOT FOUND in ${SCRIPTS_DIR}"
        MISSING=$((MISSING + 1))
    fi
done

if [ $MISSING -gt 0 ]; then
    echo ""
    echo "  ⚠  Copy missing scripts to ${SCRIPTS_DIR}/ first"
    echo "  ⚠  Then re-run this script"
    echo ""
    echo "  Scripts are in your Claude.ai downloads folder."
    echo "  mv ~/Downloads/0*.py ~/Downloads/01_rpi5_setup.sh \\"
    echo "     ${SCRIPTS_DIR}/"
    exit 1
fi

# ── Step 4: Build ARM64 container ────────────────────────────
echo ""
echo "[4/6] Building ARM64 Ubuntu 24.04 container..."
echo "  (This pulls Ubuntu 24.04 arm64 — may take a few minutes)"
echo "  (Same OS as your RPi5 — identical environment)"
echo ""

# Create a Dockerfile that mirrors our RPi5 setup exactly
cat > "${BUILD_DIR}/Dockerfile.arm64" << 'EOF'
# ── ARM64 Ubuntu 24.04 — mirrors RPi5 environment exactly ────
FROM --platform=linux/arm64 ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=America/New_York

# System packages — same as 01_rpi5_setup.sh
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y \
        python3-pip \
        python3-venv \
        python3-dev \
        python3-full \
        git \
        sqlite3 \
        can-utils \
        libffi-dev \
        libssl-dev \
        libglib2.0-dev \
        pkg-config \
        build-essential \
        usbutils \
        nano \
        curl \
        wget \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create test user (mirrors Ubuntu 24.04 RPi5 setup)
RUN useradd -m -s /bin/bash xaos && \
    usermod -aG dialout xaos

# Set up project structure
RUN mkdir -p /home/xaos/mini_obd/{logs,data,models,config,scripts} && \
    mkdir -p /home/xaos/obd_env && \
    chown -R xaos:xaos /home/xaos/

USER xaos
WORKDIR /home/xaos

# Create Python virtual environment
RUN python3 -m venv /home/xaos/obd_env --prompt "obd_env"

# Install Python packages — same as 01_rpi5_setup.sh
# Using --no-cache-dir to keep image lean
RUN /home/xaos/obd_env/bin/pip install --upgrade pip setuptools wheel && \
    /home/xaos/obd_env/bin/pip install \
        python-obd \
        pyserial \
        python-can \
        cantools \
        bleak \
        pandas \
        numpy \
        matplotlib \
        scikit-learn \
    --no-cache-dir

# Copy scripts into container
COPY --chown=xaos:xaos scripts/ /home/xaos/mini_obd/scripts/

# Default: run package verification
CMD ["/home/xaos/obd_env/bin/python", "-c", "\
import obd, serial, can, pandas, numpy, sklearn, bleak, matplotlib; \
print('=== ARM64 Package Verification ==='); \
print(f'python-obd  : {obd.__version__}'); \
print(f'pyserial    : {serial.__version__}'); \
print(f'pandas      : {pandas.__version__}'); \
print(f'numpy       : {numpy.__version__}'); \
print(f'matplotlib  : {matplotlib.__version__}'); \
print(f'scikit-learn: {sklearn.__version__}'); \
print('================================='); \
print('ALL PACKAGES OK - Ready for RPi5'); \
"]
EOF

# Build the image
docker build \
    --platform linux/arm64 \
    -f "${BUILD_DIR}/Dockerfile.arm64" \
    -t mini-obd-arm64:latest \
    "${BUILD_DIR}"

echo "  ✓ ARM64 image built: mini-obd-arm64:latest"

# ── Step 5: Verify packages ───────────────────────────────────
echo ""
echo "[5/6] Verifying all packages in ARM64 container..."
echo ""

docker run --rm \
    --platform linux/arm64 \
    mini-obd-arm64:latest

# ── Step 6: Run script syntax checks ─────────────────────────
echo ""
echo "[6/6] Checking script syntax in ARM64 Python..."
echo ""

for script in 02_test_connection.py 03_obd_logger.py 04_analyse.py; do
    echo -n "  Checking ${script}... "
    docker run --rm \
        --platform linux/arm64 \
        mini-obd-arm64:latest \
        /home/xaos/obd_env/bin/python \
        -m py_compile \
        /home/xaos/mini_obd/scripts/${script} \
        2>&1 && echo "✓ OK" || echo "✗ SYNTAX ERROR"
done

# ── Summary ───────────────────────────────────────────────────
echo ""
echo "================================================"
echo " ARM64 Build Complete!"
echo "================================================"
echo ""
echo "  Image    : mini-obd-arm64:latest"
echo "  Build dir: ${BUILD_DIR}"
echo ""
echo "  Tomorrow when RPi5 PSU arrives:"
echo ""
echo "  1. Flash Ubuntu 24.04 Server to SN7100"
echo "  2. Boot RPi5, SSH in"
echo "  3. Run setup script:"
echo "     scp ${SCRIPTS_DIR}/01_rpi5_setup.sh xaos@<PI-IP>:~/"
echo "     ssh xaos@<PI-IP> 'sudo bash ~/01_rpi5_setup.sh'"
echo ""
echo "  4. Copy remaining scripts:"
echo "     scp ${SCRIPTS_DIR}/*.py xaos@<PI-IP>:~/mini_obd/scripts/"
echo ""
echo "  5. Test K+DCAN connection:"
echo "     ssh xaos@<PI-IP>"
echo "     source ~/obd_env/bin/activate"
echo "     python ~/mini_obd/scripts/02_test_connection.py"
echo ""
echo "  Optional — run interactive ARM64 shell:"
echo "  docker run -it --platform linux/arm64 \\"
echo "    -v ${BUILD_DIR}:/home/xaos/mini_obd \\"
echo "    mini-obd-arm64:latest bash"
echo ""
