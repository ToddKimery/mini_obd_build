#!/usr/bin/env python3
"""
Mock OBD data generator for testing 04_analyse.py without Pi/car hardware.

Creates two sessions in the SQLite database:
  Session 1 — Healthy N14 baseline (warm idle, normal values)
  Session 2 — P0100/2B5F fault pattern (low MAF, climbing LTFT)

Usage:
    python ~/mini_obd/scripts/00_mock_data.py
    python ~/mini_obd/scripts/04_analyse.py --session 1
    python ~/mini_obd/scripts/04_analyse.py --session 2
"""

import sqlite3
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)

HOME    = str(Path.home())
DB_PATH = f"{HOME}/mini_obd/data/mini_obd.db"
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
Path(f"{HOME}/mini_obd/logs").mkdir(parents=True, exist_ok=True)

# ── Schema ────────────────────────────────────────────────────
conn   = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.executescript("""
    CREATE TABLE IF NOT EXISTS sessions (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        start_time TEXT NOT NULL,
        end_time   TEXT,
        port       TEXT,
        samples    INTEGER DEFAULT 0,
        note       TEXT
    );

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
    );

    CREATE INDEX IF NOT EXISTS idx_session_time
    ON readings(session_id, elapsed_s);
""")
conn.commit()

THRESHOLDS = {
    "maf_gs"   : {"idle_min": 1.5,  "idle_max": 6.0},
    "stft_pct" : {"min": -10.0, "max": 10.0},
    "ltft_pct" : {"min": -10.0, "max": 10.0},
    "coolant_c": {"min": 60.0,  "max": 110.0},
}

def noise(scale=1.0):
    return random.gauss(0, scale)

def check_anomalies(row):
    flags, reasons = [], []
    rpm = row.get("rpm")
    maf = row.get("maf_gs")
    if rpm and maf and rpm < 1100:
        t = THRESHOLDS["maf_gs"]
        if maf < t["idle_min"] or maf > t["idle_max"]:
            flags.append(True)
            reasons.append(
                f"MAF={maf:.2f}g/s outside idle [{t['idle_min']}-{t['idle_max']}]"
            )
    for key in ("stft_pct", "ltft_pct"):
        val = row.get(key)
        if val is not None:
            t = THRESHOLDS[key]
            if val < t["min"] or val > t["max"]:
                flags.append(True)
                reasons.append(
                    f"{key}={val:+.1f}% outside [{t['min']},{t['max']}]%"
                )
    ct = row.get("coolant_c")
    if ct and ct > THRESHOLDS["coolant_c"]["max"]:
        flags.append(True)
        reasons.append(f"Coolant={ct:.0f}°C OVERHEATING!")
    return bool(flags), ", ".join(reasons)

def insert_session(note):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    cursor.execute(
        "INSERT INTO sessions (start_time, port, note) VALUES (?,?,?)",
        (ts, "/dev/kdcan", note)
    )
    conn.commit()
    return cursor.lastrowid, ts

def insert_readings(session_id, rows):
    for row in rows:
        flag, reason = check_anomalies(row)
        row["anomaly_flag"]   = 1 if flag else 0
        row["anomaly_reason"] = reason if flag else ""
        cursor.execute("""
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

    cursor.execute(
        "UPDATE sessions SET end_time=?, samples=? WHERE id=?",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), len(rows), session_id)
    )
    conn.commit()

# ── Session 1: Healthy N14 baseline ──────────────────────────
# Warm idle, MAF 2.5-3.5 g/s, LTFT ±3%, a few throttle blips
print("Generating Session 1: Healthy N14 baseline...")

sid1, ts1 = insert_session("MOCK — Healthy N14 baseline")
rows1 = []
duration = 300  # 5 minutes
interval = 0.5
t = 0.0
base_time = datetime.now()

while t <= duration:
    elapsed = round(t, 2)
    ts      = (base_time + timedelta(seconds=t)).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    # Coolant warms from 85 to 92 over session (already mostly warm)
    coolant = 85.0 + (92.0 - 85.0) * (1 - math.exp(-t / 120)) + noise(0.3)

    # RPM: warm idle with occasional blip
    if 60 < t < 70 or 160 < t < 170 or 240 < t < 250:
        rpm = 2500 + noise(80)
        throttle = 18 + noise(1)
        maf      = 14 + noise(0.8)
        map_kpa  = 75 + noise(3)
        engine_load = 45 + noise(3)
        timing   = 18 + noise(1)
    else:
        rpm = 820 + noise(15)
        throttle = 3.5 + noise(0.3)
        maf      = 2.8 + noise(0.15)
        map_kpa  = 38 + noise(2)
        engine_load = 22 + noise(2)
        timing   = 8 + noise(0.5)

    stft = noise(1.5)
    ltft = 1.5 + noise(0.8)     # Healthy: slightly positive, well within ±10%
    o2_b1s1 = 0.45 + 0.35 * math.sin(t * 1.1) + noise(0.03)
    o2_b1s2 = 0.65 + noise(0.02)

    rows1.append({
        "timestamp"     : ts,
        "elapsed_s"     : elapsed,
        "maf_gs"        : round(maf, 4),
        "stft_pct"      : round(stft, 4),
        "ltft_pct"      : round(ltft, 4),
        "engine_load"   : round(engine_load, 4),
        "rpm"           : round(rpm, 1),
        "coolant_c"     : round(coolant, 2),
        "iat_c"         : round(28 + noise(1), 2),
        "throttle_pct"  : round(throttle, 2),
        "map_kpa"       : round(map_kpa, 2),
        "speed_kph"     : 0.0,
        "timing_deg"    : round(timing, 2),
        "o2_b1s1_v"     : round(max(0.05, min(0.95, o2_b1s1)), 4),
        "o2_b1s2_v"     : round(o2_b1s2, 4),
        "fuel_pressure" : round(350 + noise(5), 2),
        "barometric_kpa": round(101.3 + noise(0.1), 2),
        "run_time_s"    : round(t, 1),
    })
    t += interval

insert_readings(sid1, rows1)
print(f"  Session 1: {len(rows1)} samples, session_id={sid1}")

# ── Session 2: P0100/2B5F fault pattern ──────────────────────
# MAF reads ~35% of expected. LTFT climbs from +8% to +25%.
# RPM and MAP are plausible — DME knows something is wrong.
print("Generating Session 2: P0100/2B5F fault pattern (low MAF, climbing LTFT)...")

sid2, ts2 = insert_session("MOCK — P0100/2B5F fault: low MAF, high LTFT")
rows2 = []
duration = 420  # 7 minutes
t = 0.0
base_time = datetime.now()

while t <= duration:
    elapsed = round(t, 2)
    ts      = (base_time + timedelta(seconds=t)).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    coolant = 90.0 + noise(0.4)

    # MAF fault: reads ~0.7-1.1 g/s at idle (should be 2.5-3.5)
    # Simulates cam timing off by ~1 tooth or MAF signal dragged low
    if 120 < t < 135 or 280 < t < 295:
        # Throttle blips — MAF responds but still reads low
        rpm      = 2300 + noise(100)
        throttle = 16 + noise(1.5)
        maf      = 8 + noise(0.6)      # ~55% of expected at this RPM
        map_kpa  = 70 + noise(4)
        engine_load = 52 + noise(4)
        timing   = 16 + noise(1.5)
    else:
        rpm      = 850 + noise(20)
        throttle = 3.8 + noise(0.3)
        maf      = 0.85 + noise(0.08)  # Way too low for idle
        map_kpa  = 40 + noise(2)
        engine_load = 28 + noise(3)    # Load higher than MAF suggests (DME confused)
        timing   = 6 + noise(1)

    # LTFT climbs progressively as DME tries to correct lean condition
    # Reaches ~+22% by end of session then plateaus (hits limit, sets 2B5F)
    ltft_target = min(22.0, 8.0 + (t / duration) * 18.0)
    ltft = ltft_target + noise(0.5)

    # STFT oscillates high as DME desperately adds short-term fuel
    stft = 8.5 + 3.5 * math.sin(t * 0.3) + noise(1.2)
    stft = max(-15, min(15, stft))

    # O2 reads lean (DME still correcting, sensor sees lean exhaust)
    o2_b1s1 = 0.15 + 0.12 * math.sin(t * 0.8) + noise(0.04)  # Leaning out
    o2_b1s1 = max(0.05, min(0.95, o2_b1s1))
    o2_b1s2 = 0.55 + noise(0.03)

    rows2.append({
        "timestamp"     : ts,
        "elapsed_s"     : elapsed,
        "maf_gs"        : round(maf, 4),
        "stft_pct"      : round(stft, 4),
        "ltft_pct"      : round(ltft, 4),
        "engine_load"   : round(engine_load, 4),
        "rpm"           : round(rpm, 1),
        "coolant_c"     : round(coolant, 2),
        "iat_c"         : round(30 + noise(1.2), 2),
        "throttle_pct"  : round(throttle, 2),
        "map_kpa"       : round(map_kpa, 2),
        "speed_kph"     : 0.0,
        "timing_deg"    : round(timing, 2),
        "o2_b1s1_v"     : round(o2_b1s1, 4),
        "o2_b1s2_v"     : round(o2_b1s2, 4),
        "fuel_pressure" : round(348 + noise(6), 2),
        "barometric_kpa": round(101.3 + noise(0.1), 2),
        "run_time_s"    : round(t, 1),
    })
    t += interval

insert_readings(sid2, rows2)
print(f"  Session 2: {len(rows2)} samples, session_id={sid2}")

conn.close()
print(f"\nDatabase: {DB_PATH}")
print("Run analyser:")
print(f"  python ~/mini_obd/scripts/04_analyse.py --session 1")
print(f"  python ~/mini_obd/scripts/04_analyse.py --session 2")
