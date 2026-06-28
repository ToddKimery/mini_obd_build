#!/usr/bin/env python3
"""
============================================================
Mini Cooper R56 N14 - Step 3: OBD Data Logger
Verified for: RPi5, Ubuntu 24.04 LTS arm64, K+DCAN FT232RL
============================================================
Logs all available OBD-II PIDs to CSV + SQLite on NVMe.

Usage:
    source ~/obd_env/bin/activate
    python ~/mini_obd/scripts/03_obd_logger.py
    python ~/mini_obd/scripts/03_obd_logger.py --interval 0.25
    python ~/mini_obd/scripts/03_obd_logger.py --port /dev/ttyUSB0

Press Ctrl+C to stop logging cleanly.
============================================================
"""

import obd
import sqlite3
import csv
import time
import os
import argparse
import signal
import sys
from datetime import datetime
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────
# Ubuntu 24.04 home dir is /home/<username> NOT /home/pi
# Detect actual home directory at runtime
HOME = str(Path.home())

CONFIG = {
    "port"     : "/dev/kdcan",    # udev symlink (falls back below)
    "baudrate" : 38400,           # FT232RL UART speed (CAN bus is 500kbps on the vehicle side)
    "interval" : 0.5,             # Seconds between samples
    "log_dir"  : f"{HOME}/mini_obd/logs",
    "db_path"  : f"{HOME}/mini_obd/data/mini_obd.db",
    "timeout"  : 30,
}

# ── PIDs ──────────────────────────────────────────────────────
PID_MAP = {
    # MAF diagnosis (P0100/2B5 target)
    "maf_gs"        : obd.commands.MAF,
    "stft_pct"      : obd.commands.SHORT_FUEL_TRIM_1,
    "ltft_pct"      : obd.commands.LONG_FUEL_TRIM_1,
    "engine_load"   : obd.commands.ENGINE_LOAD,
    "rpm"           : obd.commands.RPM,
    # Engine health
    "coolant_c"     : obd.commands.COOLANT_TEMP,
    "iat_c"         : obd.commands.INTAKE_TEMP,
    "throttle_pct"  : obd.commands.THROTTLE_POS,
    "map_kpa"       : obd.commands.INTAKE_PRESSURE,
    "speed_kph"     : obd.commands.SPEED,
    "timing_deg"    : obd.commands.TIMING_ADVANCE,
    "barometric_kpa": obd.commands.BAROMETRIC_PRESSURE,
    # O2 sensors
    "o2_b1s1_v"     : obd.commands.O2_B1S1,
    "o2_b1s2_v"     : obd.commands.O2_B1S2,
    # Runtime
    "run_time_s"    : obd.commands.RUN_TIME,
    "fuel_pressure" : obd.commands.FUEL_PRESSURE,
}

# ── Anomaly Thresholds (N14 warm idle) ────────────────────────
THRESHOLDS = {
    "maf_gs"   : {"idle_min": 1.5,  "idle_max": 6.0},
    "stft_pct" : {"min": -10.0, "max": 10.0},
    "ltft_pct" : {"min": -10.0, "max": 10.0},
    "coolant_c": {"min": 60.0,  "max": 110.0},
    "iat_c"    : {"min": -20.0, "max": 70.0},
}

# ── Colours ───────────────────────────────────────────────────
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

# ── Port Resolution ───────────────────────────────────────────
def resolve_port(requested: str) -> str:
    """Find the best available serial port for K+DCAN."""
    if os.path.exists(requested):
        return requested

    # Fallback search order for Ubuntu 24.04
    fallbacks = [
        "/dev/ttyUSB0",
        "/dev/ttyUSB1",
        "/dev/ttyACM0",
    ]
    for port in fallbacks:
        if os.path.exists(port):
            print(f"  {YELLOW}!{RESET} {requested} not found, "
                  f"using fallback: {port}")
            return port

    print(f"  {RED}✗{RESET} No serial port found!")
    print("  Check: ls /dev/tty* | grep -E 'USB|ACM'")
    sys.exit(1)

# ── Database ──────────────────────────────────────────────────
def init_database(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time TEXT NOT NULL,
            end_time   TEXT,
            port       TEXT,
            samples    INTEGER DEFAULT 0,
            note       TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER,
            timestamp       TEXT NOT NULL,
            elapsed_s       REAL,
            maf_gs          REAL,
            stft_pct        REAL,
            ltft_pct        REAL,
            engine_load     REAL,
            rpm             REAL,
            coolant_c       REAL,
            iat_c           REAL,
            throttle_pct    REAL,
            map_kpa         REAL,
            speed_kph       REAL,
            timing_deg      REAL,
            o2_b1s1_v       REAL,
            o2_b1s2_v       REAL,
            fuel_pressure   REAL,
            barometric_kpa  REAL,
            run_time_s      REAL,
            anomaly_flag    INTEGER DEFAULT 0,
            anomaly_reason  TEXT,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_session_time
        ON readings(session_id, elapsed_s)
    """)

    conn.commit()
    return conn

# ── CSV ───────────────────────────────────────────────────────
FIELDNAMES = [
    "timestamp", "elapsed_s",
    "maf_gs", "stft_pct", "ltft_pct", "engine_load",
    "rpm", "coolant_c", "iat_c", "throttle_pct",
    "map_kpa", "speed_kph", "timing_deg",
    "o2_b1s1_v", "o2_b1s2_v", "fuel_pressure",
    "barometric_kpa", "run_time_s",
    "anomaly_flag", "anomaly_reason"
]

def init_csv(log_dir: str, session_ts: str):
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    path = os.path.join(log_dir, f"session_{session_ts}.csv")
    f = open(path, "w", newline="", buffering=1)  # Line-buffered
    w = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
    w.writeheader()
    return f, w, path

# ── Anomaly Detection ─────────────────────────────────────────
def check_anomalies(row: dict) -> tuple:
    flags, reasons = [], []
    rpm = row.get("rpm")
    maf = row.get("maf_gs")

    # MAF at idle
    if rpm and maf and rpm < 1100:
        t = THRESHOLDS["maf_gs"]
        if maf < t["idle_min"] or maf > t["idle_max"]:
            flags.append(True)
            reasons.append(
                f"MAF={maf:.2f}g/s outside idle [{t['idle_min']}-{t['idle_max']}]"
            )

    # Fuel trims
    for key in ("stft_pct", "ltft_pct"):
        val = row.get(key)
        if val is not None:
            t = THRESHOLDS[key]
            if val < t["min"] or val > t["max"]:
                flags.append(True)
                reasons.append(f"{key}={val:+.1f}% outside [{t['min']},{t['max']}]%")

    # Coolant overheat
    ct = row.get("coolant_c")
    if ct and ct > THRESHOLDS["coolant_c"]["max"]:
        flags.append(True)
        reasons.append(f"Coolant={ct:.0f}°C OVERHEATING!")

    return bool(flags), ", ".join(reasons)

# ── PID Query ─────────────────────────────────────────────────
def query_pid(conn, cmd):
    try:
        resp = conn.query(cmd)
        if resp.is_null():
            return None
        val = resp.value
        if hasattr(val, 'magnitude'):
            return round(float(val.magnitude), 4)
        return round(float(val), 4)
    except Exception:
        return None

# ── Main Logger ───────────────────────────────────────────────
def run_logger(args):
    session_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    start_time = time.monotonic()
    port       = resolve_port(args.port)

    print(f"\n{BOLD}{'='*55}{RESET}")
    print(f"{BOLD} Mini R56 N14 OBD Logger{RESET}")
    print(f"{BOLD} Session: {session_ts}{RESET}")
    print(f"{BOLD}{'='*55}{RESET}")
    print(f"  Port     : {port}")
    print(f"  Interval : {args.interval}s  "
          f"({1/args.interval:.1f} samples/sec)")
    print(f"  Logs     : {CONFIG['log_dir']}")
    print(f"  Database : {CONFIG['db_path']}")
    print(f"\n  {YELLOW}Press Ctrl+C to stop{RESET}\n")

    # ── Connect ───────────────────────────────────────────────
    print("Connecting...", end=" ", flush=True)
    try:
        connection = obd.OBD(
            portstr=port,
            baudrate=args.baudrate,
            fast=False,
            timeout=CONFIG["timeout"],
            check_voltage=False,
        )
    except Exception as e:
        print(f"{RED}FAILED{RESET}")
        print(f"  Error: {e}")
        sys.exit(1)

    if not connection.is_connected():
        print(f"{RED}FAILED{RESET}")
        print("  Ignition ON? Switch in CAN position?")
        sys.exit(1)

    print(f"{GREEN}OK{RESET} — {connection.protocol_name()}")

    # ── Discover PIDs ─────────────────────────────────────────
    print("Discovering PIDs...", end=" ", flush=True)
    active = {}
    for name, cmd in PID_MAP.items():
        r = connection.query(cmd)
        if not r.is_null():
            active[name] = cmd

    print(f"{GREEN}{len(active)}/{len(PID_MAP)} supported{RESET}")

    if not active:
        print(f"{RED}No PIDs responded — check connection{RESET}")
        connection.close()
        sys.exit(1)

    print(f"  Active: {', '.join(active.keys())}\n")

    # ── Init storage ──────────────────────────────────────────
    db       = init_database(CONFIG["db_path"])
    csv_f, csv_w, csv_path = init_csv(CONFIG["log_dir"], session_ts)

    cur = db.cursor()
    cur.execute(
        "INSERT INTO sessions (start_time, port) VALUES (?,?)",
        (session_ts, port)
    )
    db.commit()
    session_id = cur.lastrowid

    print(f"  CSV : {csv_path}")
    print(f"  DB  : session_id={session_id}")
    print(f"\n{'─'*62}")
    print(f"  {'t(s)':>6}  {'MAF':>6}  {'STFT':>6}  {'LTFT':>6}  "
          f"{'RPM':>5}  {'CLT':>5}  {'IAT':>5}  {'Load':>5}")
    print(f"  {'':>6}  {'g/s':>6}  {'%':>6}  {'%':>6}  "
          f"{'rpm':>5}  {'°C':>5}  {'°C':>5}  {'%':>5}")
    print(f"{'─'*62}")

    def fmt(v, w=6):
        return f"{v:>{w}.1f}" if v is not None else f"{'---':>{w}}"

    # ── Shutdown handler ──────────────────────────────────────
    running       = [True]
    sample_count  = [0]

    def _shutdown(sig, frame):
        running[0] = False

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # ── Logging loop ──────────────────────────────────────────
    while running[0]:
        t0  = time.monotonic()
        now = datetime.now()
        ela = round(time.monotonic() - start_time, 2)

        row = {
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "elapsed_s": ela,
        }
        for name, cmd in active.items():
            row[name] = query_pid(connection, cmd)

        is_anomaly, reason = check_anomalies(row)
        row["anomaly_flag"]   = 1 if is_anomaly else 0
        row["anomaly_reason"] = reason if is_anomaly else ""

        # Console display
        alert = f" {RED}⚠ {reason}{RESET}" if is_anomaly else ""
        print(
            f"  {ela:>6.1f}  {fmt(row.get('maf_gs'))}  "
            f"{fmt(row.get('stft_pct'))}  {fmt(row.get('ltft_pct'))}  "
            f"{fmt(row.get('rpm'),5)}  {fmt(row.get('coolant_c'),5)}  "
            f"{fmt(row.get('iat_c'),5)}  {fmt(row.get('engine_load'),5)}"
            f"{alert}"
        )

        # Write CSV (line-buffered — safe on power loss)
        csv_w.writerow(row)

        # Write SQLite
        try:
            cur.execute("""
                INSERT INTO readings (
                    session_id, timestamp, elapsed_s,
                    maf_gs, stft_pct, ltft_pct, engine_load,
                    rpm, coolant_c, iat_c, throttle_pct,
                    map_kpa, speed_kph, timing_deg,
                    o2_b1s1_v, o2_b1s2_v, fuel_pressure,
                    barometric_kpa, run_time_s,
                    anomaly_flag, anomaly_reason
                ) VALUES (
                    :session_id, :timestamp, :elapsed_s,
                    :maf_gs, :stft_pct, :ltft_pct, :engine_load,
                    :rpm, :coolant_c, :iat_c, :throttle_pct,
                    :map_kpa, :speed_kph, :timing_deg,
                    :o2_b1s1_v, :o2_b1s2_v, :fuel_pressure,
                    :barometric_kpa, :run_time_s,
                    :anomaly_flag, :anomaly_reason
                )
            """, {**row, "session_id": session_id})
            db.commit()
        except sqlite3.Error as e:
            print(f"{YELLOW}  DB error: {e}{RESET}")

        sample_count[0] += 1

        # Maintain interval
        sleep = max(0, args.interval - (time.monotonic() - t0))
        time.sleep(sleep)

    # ── Shutdown cleanly ──────────────────────────────────────
    print(f"\n{'─'*62}")
    print(f"\n{GREEN}Logging stopped.{RESET}")
    duration = round(time.monotonic() - start_time, 1)
    print(f"  Samples    : {sample_count[0]}")
    print(f"  Duration   : {duration}s")
    print(f"  CSV        : {csv_path}")
    print(f"  Session ID : {session_id}")

    cur.execute(
        "UPDATE sessions SET end_time=?, samples=? WHERE id=?",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
         sample_count[0], session_id)
    )
    db.commit()

    csv_f.close()
    db.close()
    connection.close()

    print(f"\n  To analyse: python ~/mini_obd/scripts/04_analyse.py "
          f"--session {session_id}\n")

# ── Entry Point ───────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Mini R56 N14 OBD Data Logger (Ubuntu 24.04 / RPi5)"
    )
    parser.add_argument(
        "--port", default=CONFIG["port"],
        help=f"Serial port (default: {CONFIG['port']})"
    )
    parser.add_argument(
        "--baudrate", type=int, default=CONFIG["baudrate"],
        help=f"Serial baud rate to FT232RL (default: {CONFIG['baudrate']})"
    )
    parser.add_argument(
        "--interval", type=float, default=CONFIG["interval"],
        help=f"Sample interval seconds (default: {CONFIG['interval']})"
    )
    run_logger(parser.parse_args())
