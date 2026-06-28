#!/usr/bin/env python3
"""
============================================================
Mini Cooper R56 N14 - Step 2: Connection Test
Verified for: RPi5, Ubuntu 24.04 LTS arm64, K+DCAN FT232RL
============================================================
Usage:
    source ~/obd_env/bin/activate
    python ~/mini_obd/scripts/02_test_connection.py

K+DCAN switch position for R56 N14:
    Switch AWAY from cable = D-CAN mode  ← USE THIS
    Switch TOWARDS cable   = K-Line mode
============================================================
"""

import sys
import os
import time
import argparse

# ── Colour helpers ───────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"

def ok(msg):   print(f"  {GREEN}✓{RESET} {msg}")
def err(msg):  print(f"  {RED}✗{RESET} {msg}")
def warn(msg): print(f"  {YELLOW}!{RESET} {msg}")
def info(msg): print(f"  {CYAN}→{RESET} {msg}")

parser = argparse.ArgumentParser(
    description="Mini R56 N14 K+DCAN Connection Test"
)
parser.add_argument(
    "--port", default=None,
    help="Serial port override (e.g. /dev/ttyUSB0). "
         "Auto-detected if omitted."
)
args = parser.parse_args()

print(f"\n{'='*55}")
print(" Mini R56 N14 - Connection Test")
print(f" Ubuntu 24.04 LTS | RPi5 | K+DCAN FT232RL")
print(f"{'='*55}\n")

# ── Check imports ────────────────────────────────────────────
print("[PRE-CHECK] Verifying Python packages...")
try:
    import obd
    ok(f"python-obd {obd.__version__}")
except ImportError:
    err("python-obd not installed")
    print("  Run: pip install python-obd")
    sys.exit(1)

try:
    import serial
    import serial.tools.list_ports
    ok(f"pyserial {serial.__version__}")
except ImportError:
    err("pyserial not installed")
    print("  Run: pip install pyserial")
    sys.exit(1)

# ── Check dialout group membership ───────────────────────────
print("\n[1] Checking serial port permissions...")
import grp, pwd

try:
    current_user = pwd.getpwuid(os.getuid()).pw_name
    dialout_gid  = grp.getgrnam("dialout").gr_gid
    user_groups  = [g.gr_gid for g in grp.getgrall()
                    if current_user in g.gr_mem]
    user_groups.append(pwd.getpwnam(current_user).pw_gid)

    if dialout_gid in user_groups:
        ok("User is in dialout group")
    else:
        warn("User NOT in dialout group!")
        print("  Run: sudo usermod -aG dialout $USER")
        print("  Then log out and back in")
except Exception:
    warn("Could not verify group membership — continuing anyway")

# ── Find K+DCAN port ─────────────────────────────────────────
print("\n[2] Scanning for K+DCAN cable (FT232RL)...")

kdcan_port = None

# Honour explicit --port override
if args.port:
    if os.path.exists(args.port):
        kdcan_port = args.port
        ok(f"Using --port override: {kdcan_port}")
    else:
        err(f"Specified port not found: {args.port}")
        sys.exit(1)
# Check udev symlink first
elif os.path.exists("/dev/kdcan"):
    kdcan_port = "/dev/kdcan"
    ok(f"Found via udev symlink: {kdcan_port}")
else:
    warn("/dev/kdcan symlink not found, scanning serial ports...")
    ports = list(serial.tools.list_ports.comports())

    if not ports:
        err("No serial ports detected at all")
        print("\n  Troubleshooting:")
        print("  - Is K+DCAN plugged into RPi5 USB port?")
        print("  - Check: lsusb | grep -i ftdi")
        print("  - Check: dmesg | tail -20 | grep -i tty")
        sys.exit(1)

    print(f"  Found {len(ports)} serial port(s):")
    for p in ports:
        print(f"    {p.device}: {p.description} "
              f"[{p.vid:04x}:{p.pid:04x}]"
              if p.vid else f"    {p.device}: {p.description}")

        # FT232RL vendor ID = 0x0403
        if p.vid == 0x0403 and p.pid in (0x6001, 0x6010):
            kdcan_port = p.device
            ok(f"Matched FT232RL at {kdcan_port}")
            break

    if not kdcan_port:
        # Try ttyUSB0 as last resort
        if os.path.exists("/dev/ttyUSB0"):
            kdcan_port = "/dev/ttyUSB0"
            warn(f"Using fallback: {kdcan_port} (FT232RL not confirmed)")
        else:
            err("K+DCAN not found!")
            print("\n  Troubleshooting:")
            print("  - lsusb | grep -i '0403'")
            print("  - dmesg | grep -i 'ftdi\\|ttyUSB'")
            print("  - Check cable switch: AWAY from cable = CAN mode")
            sys.exit(1)

# ── Test connection ───────────────────────────────────────────
print(f"\n[3] Connecting to N14 DME via {kdcan_port}...")
info("Switch on K+DCAN: AWAY from cable = D-CAN (correct for R56)")
info("Ignition must be ON (engine does not need to run)")
print()

# R56 N14 uses ISO 15765-4 CAN at 500kbps
# python-obd will auto-detect protocol if we don't force it
# but we specify for speed and reliability
connection = obd.OBD(
    portstr=kdcan_port,
    baudrate=38400,
    fast=False,
    timeout=30,
    check_voltage=False   # Skip voltage check - not reliable on all adapters
)

if not connection.is_connected():
    err("Failed to connect to DME")
    print("\n  Troubleshooting:")
    print("  - Ignition ON?")
    print("  - Switch position: AWAY from cable for R56 CAN")
    print("  - Try: python 02_test_connection.py --port /dev/ttyUSB0")
    connection.close()
    sys.exit(1)

ok(f"Connected! Protocol: {connection.protocol_name()}")

# ── Query PIDs ────────────────────────────────────────────────
print(f"\n[4] Testing PIDs critical for P0100/2B5 diagnosis...")
print(f"  {'PID':<25} {'Value':>10}  {'Unit':<8}  Status")
print(f"  {'-'*55}")

# Priority PIDs for N14 MAF diagnosis
TEST_PIDS = [
    (obd.commands.MAF,               "MAF",           "★ CRITICAL"),
    (obd.commands.SHORT_FUEL_TRIM_1, "Short Fuel Trim","★ CRITICAL"),
    (obd.commands.LONG_FUEL_TRIM_1,  "Long Fuel Trim", "★ CRITICAL"),
    (obd.commands.RPM,               "RPM",            "important"),
    (obd.commands.ENGINE_LOAD,       "Engine Load",    "important"),
    (obd.commands.COOLANT_TEMP,      "Coolant Temp",   "important"),
    (obd.commands.INTAKE_TEMP,       "IAT",            "important"),
    (obd.commands.THROTTLE_POS,      "Throttle Pos",   "info"),
    (obd.commands.INTAKE_PRESSURE,   "MAP Pressure",   "info"),
    (obd.commands.SPEED,             "Speed",          "info"),
    (obd.commands.O2_B1S1,           "O2 B1S1",        "info"),
    (obd.commands.O2_B1S2,           "O2 B1S2",        "info"),
    (obd.commands.TIMING_ADVANCE,    "Timing Advance", "info"),
    (obd.commands.BAROMETRIC_PRESSURE,"Barometric",    "info"),
]

working = []
failed  = []

for cmd, name, priority in TEST_PIDS:
    try:
        resp = connection.query(cmd)
        if not resp.is_null():
            val = resp.value
            mag = round(float(val.magnitude), 2) \
                  if hasattr(val, 'magnitude') else str(val)
            unit = str(val.units) if hasattr(val, 'units') else ""
            marker = GREEN + "✓" + RESET
            print(f"  {marker} {name:<23} {mag:>10}  {unit:<8}  {priority}")
            working.append(name)
        else:
            marker = YELLOW + "?" + RESET
            print(f"  {marker} {name:<23} {'---':>10}  {'':8}  no response")
            failed.append(name)
    except Exception as e:
        marker = RED + "✗" + RESET
        print(f"  {marker} {name:<23} {'ERR':>10}  {'':8}  {e}")
        failed.append(name)
    time.sleep(0.15)  # Small delay between queries

# ── N14 idle diagnosis ────────────────────────────────────────
print(f"\n[5] N14 Idle Analysis (if engine running)...")

try:
    rpm_r  = connection.query(obd.commands.RPM)
    maf_r  = connection.query(obd.commands.MAF)
    ltft_r = connection.query(obd.commands.LONG_FUEL_TRIM_1)
    stft_r = connection.query(obd.commands.SHORT_FUEL_TRIM_1)

    rpm  = float(rpm_r.value.magnitude)  if not rpm_r.is_null()  else None
    maf  = float(maf_r.value.magnitude)  if not maf_r.is_null()  else None
    ltft = float(ltft_r.value.magnitude) if not ltft_r.is_null() else None
    stft = float(stft_r.value.magnitude) if not stft_r.is_null() else None

    if rpm and rpm > 500:
        info(f"Engine running at {rpm:.0f} RPM")
        if rpm < 1100:
            info("Idle condition — checking MAF range...")
            if maf is not None:
                if 1.5 <= maf <= 6.0:
                    ok(f"MAF {maf:.2f} g/s — within idle normal range (1.5-6.0)")
                elif maf < 1.5:
                    err(f"MAF {maf:.2f} g/s — TOO LOW (expected 1.5-6.0 at idle)")
                    warn("→ Possible: bad signal, wiring, or DME power issue")
                else:
                    err(f"MAF {maf:.2f} g/s — TOO HIGH (expected 1.5-6.0 at idle)")
                    warn("→ Possible: air leak before MAF, rich condition")

            if ltft is not None:
                if abs(ltft) <= 10:
                    ok(f"LTFT {ltft:+.1f}% — within normal range (±10%)")
                elif ltft > 10:
                    err(f"LTFT {ltft:+.1f}% — POSITIVE (DME adding fuel = running LEAN)")
                    warn("→ MAF reading LOW — supports P0100/2B5 diagnosis")
                else:
                    err(f"LTFT {ltft:+.1f}% — NEGATIVE (DME removing fuel = running RICH)")
    else:
        info("Engine not running (ignition on only) — idle analysis skipped")

except Exception as e:
    warn(f"Idle analysis skipped: {e}")

# ── Summary ───────────────────────────────────────────────────
print(f"\n{'='*55}")
print(" Summary")
print(f"{'='*55}")
print(f"  Working PIDs : {GREEN}{len(working)}{RESET}/{len(TEST_PIDS)}")
print(f"  Failed PIDs  : {RED}{len(failed)}{RESET}/{len(TEST_PIDS)}")
print(f"  Port used    : {kdcan_port}")
print(f"  Protocol     : {connection.protocol_name()}")

if len(working) >= 6:
    ok("Connection healthy — ready for full logging!")
    print(f"\n  Next: python ~/mini_obd/scripts/03_obd_logger.py")
elif len(working) >= 3:
    warn("Partial connection — MAF and fuel trim PIDs responding")
    warn("May still be sufficient for diagnosis")
else:
    err("Poor connection — check switch position and ignition")

connection.close()
print()
