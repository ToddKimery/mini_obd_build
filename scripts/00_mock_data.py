#!/usr/bin/env python3
"""
Mock OBD data generator for testing 04_analyse.py and the FastAPI backend
without Pi/car hardware.

Creates two sessions in the SQLite database:
  Session 1 — Healthy N14 baseline (warm idle, normal values)
  Session 2 — P0100/2B5F fault pattern (low MAF, climbing LTFT)

Schema matches obd_manager.py exactly so both the API and the analyser
work against the same DB.

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

DB_PATH = Path.home() / "mini_obd" / "data" / "mini_obd.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
(Path.home() / "mini_obd" / "logs").mkdir(parents=True, exist_ok=True)

# ── Schema — must match obd_manager.py _init_db() exactly ────────────────────
conn = sqlite3.connect(DB_PATH)
conn.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        session_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at   TEXT NOT NULL,
        port         TEXT,
        protocol     TEXT,
        notes        TEXT
    )
""")
conn.execute("""
    CREATE TABLE IF NOT EXISTS readings (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id   INTEGER NOT NULL REFERENCES sessions(session_id),
        ts           TEXT NOT NULL,
        elapsed_s    REAL,
        rpm          REAL, coolant_c REAL, maf_gs REAL,
        throttle_pct REAL, map_kpa REAL, iat_c REAL,
        speed_kph    REAL, stft_pct REAL, ltft_pct REAL,
        timing_deg   REAL, o2_b1s1_v REAL, o2_b1s2_v REAL,
        anomaly_flag    INTEGER DEFAULT 0,
        anomaly_reason  TEXT DEFAULT ''
    )
""")
conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_session_time
    ON readings(session_id, elapsed_s)
""")
conn.commit()

# ── Thresholds (mirror obd_manager.py) ───────────────────────────────────────
THRESHOLDS = {
    "maf_gs":      {"min": 0.5,  "max": 25.0},
    "ltft_pct":    {"min": -15,  "max": 15},
    "combined_ft": {"min": -20,  "max": 20},
    "coolant_c":   {"min": 70,   "max": 115},
}

def noise(scale=1.0):
    return random.gauss(0, scale)

def check_anomaly(row):
    reasons = []
    maf  = row.get("maf_gs")
    stft = row.get("stft_pct")
    ltft = row.get("ltft_pct")
    if maf is not None and (maf < THRESHOLDS["maf_gs"]["min"] or maf > THRESHOLDS["maf_gs"]["max"]):
        reasons.append(f"MAF={maf:.2f} g/s out of range")
    if ltft is not None:
        if ltft < THRESHOLDS["ltft_pct"]["min"] or ltft > THRESHOLDS["ltft_pct"]["max"]:
            reasons.append(f"LTFT={ltft:.1f}% out of range")
        if stft is not None:
            combined = stft + ltft
            if combined < THRESHOLDS["combined_ft"]["min"] or combined > THRESHOLDS["combined_ft"]["max"]:
                reasons.append(f"STFT+LTFT={combined:.1f}% critical")
    cool = row.get("coolant_c")
    if cool is not None and (cool < THRESHOLDS["coolant_c"]["min"] or cool > THRESHOLDS["coolant_c"]["max"]):
        reasons.append(f"coolant={cool:.0f}°C out of range")
    return (1 if reasons else 0), "; ".join(reasons)

def insert_session(notes, protocol="ISO 15765-4 (CAN 11/500)"):
    cur = conn.execute(
        "INSERT INTO sessions (started_at, port, protocol, notes) VALUES (?,?,?,?)",
        (datetime.now().isoformat(), "/dev/kdcan", protocol, notes),
    )
    conn.commit()
    return cur.lastrowid

def insert_readings(session_id, rows):
    for row in rows:
        flag, reason = check_anomaly(row)
        conn.execute("""
            INSERT INTO readings (
                session_id, ts, elapsed_s,
                rpm, coolant_c, maf_gs, throttle_pct, map_kpa, iat_c,
                speed_kph, stft_pct, ltft_pct, timing_deg,
                o2_b1s1_v, o2_b1s2_v, anomaly_flag, anomaly_reason
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            session_id, row["ts"], row["elapsed_s"],
            row["rpm"], row["coolant_c"], row["maf_gs"],
            row["throttle_pct"], row["map_kpa"], row["iat_c"],
            row["speed_kph"], row["stft_pct"], row["ltft_pct"],
            row["timing_deg"], row["o2_b1s1_v"], row["o2_b1s2_v"],
            flag, reason,
        ))
    conn.commit()

# ── Session 1: Healthy N14 baseline ──────────────────────────────────────────
print("Generating Session 1: Healthy N14 baseline...")

sid1 = insert_session("MOCK — Healthy N14 baseline")
rows1 = []
base_time = datetime.now()
t = 0.0
while t <= 300:
    elapsed = round(t, 2)
    ts = (base_time + timedelta(seconds=t)).isoformat()
    coolant = 85.0 + (92.0 - 85.0) * (1 - math.exp(-t / 120)) + noise(0.3)
    if 60 < t < 70 or 160 < t < 170 or 240 < t < 250:
        rpm = 2500 + noise(80);  throttle = 18 + noise(1)
        maf = 14 + noise(0.8);   map_kpa  = 75 + noise(3)
        timing = 18 + noise(1)
    else:
        rpm = 820 + noise(15);   throttle = 3.5 + noise(0.3)
        maf = 2.8 + noise(0.15); map_kpa  = 38 + noise(2)
        timing = 8 + noise(0.5)
    stft = noise(1.5)
    ltft = 1.5 + noise(0.8)
    o2_b1s1 = max(0.05, min(0.95, 0.45 + 0.35 * math.sin(t * 1.1) + noise(0.03)))
    rows1.append({
        "ts": ts, "elapsed_s": elapsed,
        "maf_gs": round(maf, 4),       "stft_pct": round(stft, 4),
        "ltft_pct": round(ltft, 4),    "rpm": round(rpm, 1),
        "coolant_c": round(coolant, 2),"iat_c": round(28 + noise(1), 2),
        "throttle_pct": round(throttle, 2), "map_kpa": round(map_kpa, 2),
        "speed_kph": 0.0,              "timing_deg": round(timing, 2),
        "o2_b1s1_v": round(o2_b1s1, 4), "o2_b1s2_v": round(0.65 + noise(0.02), 4),
    })
    t += 0.5

insert_readings(sid1, rows1)
anomalies1 = sum(1 for r in rows1 if check_anomaly(r)[0])
print(f"  Session 1: {len(rows1)} samples, session_id={sid1}, anomalies={anomalies1}")

# ── Session 2: P0100/2B5F fault pattern ──────────────────────────────────────
print("Generating Session 2: P0100/2B5F fault pattern (low MAF, climbing LTFT)...")

sid2 = insert_session("MOCK — P0100/2B5F fault: low MAF, climbing LTFT")
rows2 = []
base_time = datetime.now()
t = 0.0
while t <= 420:
    elapsed = round(t, 2)
    ts = (base_time + timedelta(seconds=t)).isoformat()
    coolant = 90.0 + noise(0.4)
    if 120 < t < 135 or 280 < t < 295:
        rpm = 2300 + noise(100); throttle = 16 + noise(1.5)
        maf = 8 + noise(0.6);   map_kpa  = 70 + noise(4)
        timing = 16 + noise(1.5)
    else:
        rpm = 850 + noise(20);   throttle = 3.8 + noise(0.3)
        maf = 0.85 + noise(0.08); map_kpa = 40 + noise(2)
        timing = 6 + noise(1)
    ltft = min(22.0, 8.0 + (t / 420) * 18.0) + noise(0.5)
    stft = max(-15, min(15, 8.5 + 3.5 * math.sin(t * 0.3) + noise(1.2)))
    o2_b1s1 = max(0.05, min(0.95, 0.15 + 0.12 * math.sin(t * 0.8) + noise(0.04)))
    rows2.append({
        "ts": ts, "elapsed_s": elapsed,
        "maf_gs": round(maf, 4),       "stft_pct": round(stft, 4),
        "ltft_pct": round(ltft, 4),    "rpm": round(rpm, 1),
        "coolant_c": round(coolant, 2),"iat_c": round(30 + noise(1.2), 2),
        "throttle_pct": round(throttle, 2), "map_kpa": round(map_kpa, 2),
        "speed_kph": 0.0,              "timing_deg": round(timing, 2),
        "o2_b1s1_v": round(o2_b1s1, 4), "o2_b1s2_v": round(0.55 + noise(0.03), 4),
    })
    t += 0.5

insert_readings(sid2, rows2)
anomalies2 = sum(1 for r in rows2 if check_anomaly(r)[0])
print(f"  Session 2: {len(rows2)} samples, session_id={sid2}, anomalies={anomalies2}")

conn.close()
print(f"\nDatabase: {DB_PATH}")
print("Run analyser:")
print(f"  python ~/mini_obd/scripts/04_analyse.py --session {sid1}")
print(f"  python ~/mini_obd/scripts/04_analyse.py --session {sid2}")
