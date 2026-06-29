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

# CAN + SocketCAN — pure Python, no C extensions
RUN /root/obd_env/bin/pip install --prefer-binary \
        python-can \
        cantools

# ── Verify installs ───────────────────────────────────────────
RUN /root/obd_env/bin/python3 -c "\
import can, pandas, numpy, sklearn, matplotlib; \
print('All packages OK'); \
print(f'  python-can {can.__version__}'); \
print(f'  pandas     {pandas.__version__}'); \
print(f'  numpy      {numpy.__version__}'); \
"

# ── Project structure (mirrors 01_rpi5_setup.sh step 3) ──────
RUN mkdir -p /root/mini_obd/logs \
             /root/mini_obd/data \
             /root/mini_obd/models \
             /root/mini_obd/config \
             /root/mini_obd/scripts

# ── API packages ─────────────────────────────────────────────
RUN /root/obd_env/bin/pip install --prefer-binary \
        fastapi \
        "uvicorn[standard]" \
        websockets \
        python-multipart \
        aiofiles \
        anthropic

# ── Bake version at build time ────────────────────────────────
ARG BUILD_VERSION=dev
ARG BUILD_DATE=
RUN printf '%s\n%s\n' "${BUILD_VERSION}" "${BUILD_DATE}" > /root/mini_obd/VERSION

# ── Copy scripts + app ────────────────────────────────────────
COPY scripts/ /root/mini_obd/scripts/
COPY app/api/  /root/mini_obd/app/api/
COPY app/web/out/ /root/mini_obd/app/web/out/

# ── Activate venv by default ──────────────────────────────────
ENV PATH="/root/obd_env/bin:$PATH"
ENV VIRTUAL_ENV="/root/obd_env"

WORKDIR /root/mini_obd/app/api

RUN chmod +x /root/mini_obd/scripts/start.sh

EXPOSE 8080
# HTTP for local dev (localhost is treated as secure by Chrome — SW + PWA work)
# Pi deployment uses start.sh which generates a self-signed cert and runs HTTPS
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
