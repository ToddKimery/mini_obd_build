# Ubuntu 24.04 arm64 — matches RPi5 target environment exactly
FROM ubuntu:24.04

# Prevent interactive prompts during apt
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1

# ── System packages (mirrors 01_rpi5_setup.sh step 2) ────────
RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-venv \
    python3-dev \
    python3-full \
    git \
    sqlite3 \
    usbutils \
    libffi-dev \
    libssl-dev \
    libglib2.0-dev \
    pkg-config \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── Create obd_env venv (mirrors 01_rpi5_setup.sh step 4) ────
RUN python3 -m venv /root/obd_env --prompt "obd_env"

# ── Python packages (mirrors 01_rpi5_setup.sh step 5) ────────
RUN /root/obd_env/bin/pip install --upgrade pip setuptools wheel

# Data science stack — prefer binary wheels to avoid compiling under QEMU
RUN /root/obd_env/bin/pip install --prefer-binary \
        pandas \
        numpy \
        matplotlib \
        scikit-learn

# OBD + serial — pure Python, no C extensions
RUN /root/obd_env/bin/pip install --prefer-binary \
        pyserial \
        python-can \
        cantools \
        bleak

# python-obd: try PyPI name first, fall back to 'obd' package name
RUN /root/obd_env/bin/pip install --prefer-binary python-obd \
    || /root/obd_env/bin/pip install --prefer-binary obd

# ── Verify installs ───────────────────────────────────────────
RUN /root/obd_env/bin/python3 -c "\
import obd, serial, can, pandas, numpy, sklearn, bleak, matplotlib; \
print('All packages OK'); \
print(f'  obd      {obd.__version__}'); \
print(f'  pyserial {serial.__version__}'); \
print(f'  pandas   {pandas.__version__}'); \
print(f'  numpy    {numpy.__version__}'); \
"

# ── Project structure (mirrors 01_rpi5_setup.sh step 3) ──────
RUN mkdir -p /root/mini_obd/logs \
             /root/mini_obd/data \
             /root/mini_obd/models \
             /root/mini_obd/config \
             /root/mini_obd/scripts

# ── Copy scripts ──────────────────────────────────────────────
COPY scripts/ /root/mini_obd/scripts/

# ── Activate venv by default ──────────────────────────────────
ENV PATH="/root/obd_env/bin:$PATH"
ENV VIRTUAL_ENV="/root/obd_env"

WORKDIR /root/mini_obd
