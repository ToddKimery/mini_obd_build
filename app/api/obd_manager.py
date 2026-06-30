"""
OBD connection manager — runs the read loop in a background thread,
puts each sample into an asyncio Queue for WebSocket broadcasting,
and writes to SQLite (same schema as scripts/03_obd_logger.py).

Uses python-can with SocketCAN (slcan0) for OBD2 over ISO 15765-4.
"""
import asyncio
import csv
import math
import random
import sqlite3
import threading
import time
import io
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Thresholds (must match 03_obd_logger.py) ─────────────────────────────────
THRESHOLDS = {
    "maf_gs":       {"min": 0.5,  "max": 25.0},
    "ltft_pct":     {"min": -15,  "max": 15},
    "combined_ft":  {"min": -20,  "max": 20},
    "coolant_c":    {"min": 70,   "max": 115},
}

# ── OBD2 Mode 01 PID table (ISO 15765-4) ─────────────────────────────────────
# key -> (pid_byte, decoder(data_bytes_after_pid) -> float)
CAN_PIDS: dict[str, tuple[int, ...]] = {
    "rpm":           (0x0C,),
    "coolant_c":     (0x05,),
    "maf_gs":        (0x10,),
    "throttle_pct":  (0x11,),
    "map_kpa":       (0x0B,),
    "iat_c":         (0x0F,),
    "speed_kph":     (0x0D,),
    "stft_pct":      (0x06,),
    "ltft_pct":      (0x07,),
    "timing_deg":    (0x0E,),
    "o2_b1s1_v":     (0x14,),
    "o2_b1s2_v":     (0x15,),
}


def _decode_pid(pid: int, data: bytes) -> Optional[float]:
    """Decode OBD2 Mode 01 response bytes (starting after PID echo)."""
    d = data
    if pid == 0x0C: return (d[0] * 256 + d[1]) / 4        # RPM
    if pid == 0x05: return d[0] - 40                        # coolant °C
    if pid == 0x10: return (d[0] * 256 + d[1]) / 100       # MAF g/s
    if pid == 0x11: return d[0] * 100 / 255                 # throttle %
    if pid == 0x0B: return float(d[0])                      # MAP kPa
    if pid == 0x0F: return d[0] - 40                        # IAT °C
    if pid == 0x0D: return float(d[0])                      # speed km/h
    if pid == 0x06: return (d[0] - 128) * 100 / 128        # STFT %
    if pid == 0x07: return (d[0] - 128) * 100 / 128        # LTFT %
    if pid == 0x0E: return d[0] / 2 - 64                   # timing advance °
    if pid == 0x14: return d[0] / 200                       # O2 B1S1 V
    if pid == 0x15: return d[0] / 200                       # O2 B1S2 V
    return None

DTC_DESCRIPTIONS: dict[str, str] = {
    "P0011": "Camshaft position actuator open – Bank 1 Intake",
    "P0012": "Camshaft position over-retarded – Bank 1 Intake",
    "P0014": "Camshaft position over-advanced – Bank 1 Exhaust",
    "P0016": "Crankshaft/camshaft correlation – Bank 1 Intake A",
    "P0017": "Crankshaft/camshaft correlation – Bank 1 Exhaust A",
    "P0100": "Mass air flow sensor circuit",
    "P0101": "Mass air flow circuit range/performance",
    "P0102": "Mass air flow circuit low input",
    "P0103": "Mass air flow circuit high input",
    "P0104": "Mass air flow circuit intermittent",
    "P0110": "Intake air temperature sensor circuit",
    "P0111": "Intake air temperature range/performance",
    "P0112": "Intake air temperature sensor low",
    "P0113": "Intake air temperature sensor high",
    "P0115": "Engine coolant temperature sensor circuit",
    "P0116": "Engine coolant temperature range/performance",
    "P0117": "Engine coolant temperature sensor low",
    "P0118": "Engine coolant temperature sensor high",
    "P0120": "Throttle position sensor A circuit",
    "P0121": "Throttle position sensor A range/performance",
    "P0122": "Throttle position sensor A low",
    "P0123": "Throttle position sensor A high",
    "P0130": "O2 sensor circuit – Bank 1 Sensor 1",
    "P0133": "O2 sensor slow response – Bank 1 Sensor 1",
    "P0136": "O2 sensor circuit – Bank 1 Sensor 2",
    "P0171": "Fuel system too lean – Bank 1",
    "P0172": "Fuel system too rich – Bank 1",
    "P0190": "Fuel rail pressure sensor circuit",
    "P0191": "Fuel rail pressure sensor range/performance",
    "P0192": "Fuel rail pressure sensor low",
    "P0193": "Fuel rail pressure sensor high",
    "P0234": "Turbocharger overboost condition",
    "P0236": "Turbocharger boost sensor A range/performance",
    "P0237": "Turbocharger boost sensor A low",
    "P0238": "Turbocharger boost sensor A high",
    "P0300": "Random/multiple cylinder misfire",
    "P0301": "Cylinder 1 misfire",
    "P0302": "Cylinder 2 misfire",
    "P0303": "Cylinder 3 misfire",
    "P0304": "Cylinder 4 misfire",
    "P0340": "Camshaft position sensor circuit – Bank 1",
    "P0341": "Camshaft position sensor range/performance",
    "P0420": "Catalyst efficiency below threshold – Bank 1",
    "P0441": "EVAP system incorrect purge flow",
    "P0442": "EVAP system small leak",
    "P0455": "EVAP system large leak",
    "P0456": "EVAP system very small leak",
    "P2B5F": "Mass air flow plausibility low (BMW/MINI)",
}

DB_PATH = Path.home() / "mini_obd" / "data" / "mini_obd.db"
CSV_DIR  = Path.home() / "mini_obd" / "data"


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at   TEXT NOT NULL,
            port         TEXT,
            protocol     TEXT,
            notes        TEXT,
            locked       INTEGER DEFAULT 0
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
            anomaly_flag INTEGER DEFAULT 0,
            anomaly_reason TEXT DEFAULT ''
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ai_reports (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id    INTEGER NOT NULL UNIQUE REFERENCES sessions(session_id),
            created_at    TEXT NOT NULL,
            model         TEXT,
            text          TEXT NOT NULL,
            input_tokens  INTEGER,
            output_tokens INTEGER
        )
    """)
    conn.commit()


def _detect_anomaly(row: dict) -> tuple[int, str]:
    reasons = []
    maf = row.get("maf_gs")
    stft = row.get("stft_pct")
    ltft = row.get("ltft_pct")
    if maf is not None:
        if maf < THRESHOLDS["maf_gs"]["min"] or maf > THRESHOLDS["maf_gs"]["max"]:
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
    flag = 1 if reasons else 0
    return flag, "; ".join(reasons)


class OBDManager:
    def __init__(self) -> None:
        self._conn: Optional[object] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self.data_queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._session_id: Optional[int] = None
        self._sample_count = 0
        self._start_time: Optional[float] = None
        self._port: Optional[str] = None
        self._protocol: Optional[str] = None
        self._connected = False

    # ── Public API ────────────────────────────────────────────────────────────

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def status(self) -> dict:
        elapsed = (time.monotonic() - self._start_time) if self._start_time else 0
        return {
            "connected": self._connected,
            "logging":   self._running,
            "session_id":self._session_id,
            "port":      self._port,
            "protocol":  self._protocol,
            "sample_count": self._sample_count,
            "elapsed_s": round(elapsed, 1),
        }

    async def start(self, port: Optional[str] = None, mock: bool = False) -> dict:
        if self._running:
            return {"ok": False, "error": "Already logging"}
        self._loop = asyncio.get_running_loop()
        if mock:
            self._thread = threading.Thread(target=self._mock_loop, daemon=True)
        else:
            self._thread = threading.Thread(target=self._log_loop, args=(port,), daemon=True)
        self._thread.start()
        return {"ok": True}

    async def stop(self) -> dict:
        self._running = False
        self._connected = False
        self._emit({"type": "status", "connected": False, "logging": False,
                    "session_id": self._session_id, "port": None, "protocol": None,
                    "sample_count": self._sample_count, "elapsed_s": 0})
        if self._thread:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._thread.join, 5)
        return {"ok": True, "session_id": self._session_id}

    def get_sessions(self) -> list[dict]:
        if not DB_PATH.exists():
            return []
        with sqlite3.connect(DB_PATH) as db:
            self._ensure_locked_column(db)
            db.row_factory = sqlite3.Row
            rows = db.execute("""
                SELECT s.session_id, s.started_at, s.port, s.protocol, s.notes,
                       s.locked,
                       COUNT(r.id) as sample_count,
                       MAX(r.elapsed_s) as duration_s,
                       SUM(r.anomaly_flag) as anomaly_count
                FROM sessions s
                LEFT JOIN readings r ON r.session_id = s.session_id
                GROUP BY s.session_id
                ORDER BY s.session_id DESC
            """).fetchall()
            return [dict(r) for r in rows]

    def get_session_data(self, session_id: int) -> dict:
        if not DB_PATH.exists():
            return {"error": "No database"}
        with sqlite3.connect(DB_PATH) as db:
            db.row_factory = sqlite3.Row
            session = db.execute(
                "SELECT * FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            if not session:
                return {"error": "Session not found"}
            readings = db.execute(
                "SELECT * FROM readings WHERE session_id=? ORDER BY elapsed_s",
                (session_id,)
            ).fetchall()
            return {
                "session": dict(session),
                "readings": [dict(r) for r in readings],
            }

    def get_cached_ai_report(self, session_id: int) -> Optional[dict]:
        """Return a previously saved AI report, or None if not yet generated."""
        if not DB_PATH.exists():
            return None
        with sqlite3.connect(DB_PATH) as db:
            self._ensure_ai_reports_table(db)
            db.row_factory = sqlite3.Row
            row = db.execute(
                "SELECT * FROM ai_reports WHERE session_id=?", (session_id,)
            ).fetchone()
            return dict(row) if row else None

    def save_ai_report(self, session_id: int, result: dict) -> str:
        """Persist an AI report to the database (upsert by session_id). Returns created_at."""
        created_at = datetime.now().isoformat()
        with sqlite3.connect(DB_PATH) as db:
            self._ensure_ai_reports_table(db)
            db.execute("""
                INSERT OR REPLACE INTO ai_reports
                    (session_id, created_at, model, text, input_tokens, output_tokens)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                session_id, created_at,
                result.get("model"), result.get("text"),
                result.get("input_tokens"), result.get("output_tokens"),
            ))
            db.commit()
        return created_at

    def lock_session(self, session_id: int, locked: bool) -> dict:
        if not DB_PATH.exists():
            return {"error": "No database"}
        with sqlite3.connect(DB_PATH) as db:
            self._ensure_locked_column(db)
            rows = db.execute(
                "UPDATE sessions SET locked=? WHERE session_id=?",
                (1 if locked else 0, session_id)
            ).rowcount
        if rows == 0:
            return {"error": "Session not found"}
        return {"ok": True, "locked": locked}

    def delete_session(self, session_id: int) -> dict:
        if not DB_PATH.exists():
            return {"error": "No database"}
        with sqlite3.connect(DB_PATH) as db:
            self._ensure_locked_column(db)
            db.row_factory = sqlite3.Row
            row = db.execute(
                "SELECT locked FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            if not row:
                return {"error": "Session not found"}
            if row["locked"]:
                return {"error": "Session is locked — unlock before deleting"}
            db.execute("DELETE FROM readings   WHERE session_id=?", (session_id,))
            db.execute("DELETE FROM ai_reports WHERE session_id=?", (session_id,))
            db.execute("DELETE FROM sessions   WHERE session_id=?", (session_id,))
            db.commit()
        return {"ok": True}

    @staticmethod
    def _ensure_locked_column(conn: sqlite3.Connection) -> None:
        """Migrate existing databases that pre-date the locked column."""
        try:
            conn.execute("ALTER TABLE sessions ADD COLUMN locked INTEGER DEFAULT 0")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists

    @staticmethod
    def _ensure_ai_reports_table(conn: sqlite3.Connection) -> None:
        """Migrate existing databases that pre-date the ai_reports table."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_reports (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id    INTEGER NOT NULL UNIQUE REFERENCES sessions(session_id),
                created_at    TEXT NOT NULL,
                model         TEXT,
                text          TEXT NOT NULL,
                input_tokens  INTEGER,
                output_tokens INTEGER
            )
        """)
        conn.commit()

    def get_or_generate_plot(self, session_id: int) -> Optional[bytes]:
        """Return PNG bytes for session plot."""
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import pandas as pd
        except ImportError:
            return None

        data = self.get_session_data(session_id)
        if "error" in data or not data["readings"]:
            return None

        df = pd.DataFrame(data["readings"])
        if df.empty:
            return None

        fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
        fig.patch.set_facecolor("#0f172a")
        for ax in axes:
            ax.set_facecolor("#1e293b")
            ax.tick_params(colors="#94a3b8")
            ax.spines[:].set_color("#334155")

        x = df["elapsed_s"]

        if "maf_gs" in df:
            axes[0].plot(x, df["maf_gs"], color="#38bdf8", label="MAF g/s")
            axes[0].axhspan(1.5, 6.0, alpha=0.15, color="#22c55e", label="Normal idle")
            axes[0].set_ylabel("MAF (g/s)", color="#94a3b8")
            axes[0].legend(facecolor="#1e293b", labelcolor="#e2e8f0", fontsize=8)

        for col, color, label in [("stft_pct","#facc15","STFT"), ("ltft_pct","#f97316","LTFT")]:
            if col in df:
                axes[1].plot(x, df[col], color=color, label=label)
        axes[1].axhline(0, color="#475569", linewidth=0.8, linestyle="--")
        axes[1].axhspan(-10, 10, alpha=0.1, color="#22c55e")
        axes[1].set_ylabel("Fuel Trim (%)", color="#94a3b8")
        axes[1].legend(facecolor="#1e293b", labelcolor="#e2e8f0", fontsize=8)

        if "rpm" in df:
            axes[2].plot(x, df["rpm"], color="#a78bfa", label="RPM")
            axes[2].set_ylabel("RPM", color="#94a3b8")
            axes[2].legend(facecolor="#1e293b", labelcolor="#e2e8f0", fontsize=8)

        anomalies = df[df["anomaly_flag"] == 1] if "anomaly_flag" in df.columns else df.iloc[:0]
        for ax in axes:
            for _, row in anomalies.iterrows():
                ax.axvline(row["elapsed_s"], color="#ef4444", alpha=0.3, linewidth=0.8)

        axes[2].set_xlabel("Elapsed (s)", color="#94a3b8")
        session_info = data["session"]
        fig.suptitle(
            f"Session {session_id} — {session_info.get('started_at','')[:19]}",
            color="#e2e8f0", fontsize=11
        )
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=120, bbox_inches="tight",
                    facecolor="#0f172a")
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    # ── Background thread ─────────────────────────────────────────────────────

    def _mock_loop(self) -> None:
        """Simulate the P0100/2B5F fault pattern for UI testing."""
        random.seed()
        self._connected = True
        self._port = "mock"
        self._protocol = "Mock / No hardware"
        self._running = True
        self._start_time = time.monotonic()
        self._sample_count = 0

        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(DB_PATH)
        _init_db(db)
        cur = db.execute(
            "INSERT INTO sessions (started_at, port, protocol, notes) VALUES (?,?,?,?)",
            (datetime.now().isoformat(), "mock", "Mock / No hardware", "Mock session"),
        )
        db.commit()
        self._session_id = cur.lastrowid

        self._emit({"type": "status", **self.status()})

        t = 0.0
        while self._running:
            elapsed = round(time.monotonic() - self._start_time, 2)
            # Simulate fault pattern: MAF low at idle, LTFT climbing
            rpm     = 820 + random.gauss(0, 15)
            maf     = 0.85 + random.gauss(0, 0.08)   # too low — fault
            ltft    = min(22.0, 8.0 + (t / 300) * 18.0) + random.gauss(0, 0.5)
            stft    = max(-15, min(15, 8.5 + 3.5 * math.sin(t * 0.3) + random.gauss(0, 1.2)))
            coolant = 90.0 + random.gauss(0, 0.4)
            map_kpa = 40 + random.gauss(0, 2)
            o2      = max(0.05, min(0.95, 0.15 + 0.12 * math.sin(t * 0.8) + random.gauss(0, 0.04)))

            row = {
                "ts": datetime.now().isoformat(), "elapsed_s": elapsed,
                "rpm": round(rpm, 1),       "maf_gs": round(maf, 3),
                "stft_pct": round(stft, 2), "ltft_pct": round(ltft, 2),
                "coolant_c": round(coolant, 1), "map_kpa": round(map_kpa, 1),
                "iat_c": 28.0, "throttle_pct": 3.5, "speed_kph": 0.0,
                "timing_deg": round(6 + random.gauss(0, 1), 1),
                "o2_b1s1_v": round(o2, 3), "o2_b1s2_v": round(0.55 + random.gauss(0, 0.02), 3),
            }
            flag, reason = _detect_anomaly(row)
            row["anomaly_flag"] = flag
            row["anomaly_reason"] = reason

            db.execute("""
                INSERT INTO readings (
                    session_id, ts, elapsed_s, rpm, coolant_c, maf_gs,
                    throttle_pct, map_kpa, iat_c, speed_kph, stft_pct, ltft_pct,
                    timing_deg, o2_b1s1_v, o2_b1s2_v, anomaly_flag, anomaly_reason
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (self._session_id, row["ts"], elapsed, row["rpm"], row["coolant_c"],
                  row["maf_gs"], row["throttle_pct"], row["map_kpa"], row["iat_c"],
                  row["speed_kph"], row["stft_pct"], row["ltft_pct"], row["timing_deg"],
                  row["o2_b1s1_v"], row["o2_b1s2_v"], flag, reason))
            db.commit()

            self._sample_count += 1
            row["type"] = "reading"
            row["sample_count"] = self._sample_count
            self._emit(row)
            t += 1.0
            time.sleep(1.0)

        db.close()
        self._connected = False
        self._running = False
        self._emit({"type": "status", "connected": False, "logging": False,
                    "session_id": self._session_id})

    def _log_loop(self, port: Optional[str]) -> None:
        try:
            import can
        except ImportError:
            self._emit({"type": "error", "msg": "python-can not installed"})
            return

        iface = self._find_can_interface()
        if not iface:
            self._emit({"type": "error", "msg": "No SocketCAN interface found (slcan0/can0). Is the adapter plugged in?"})
            return

        try:
            bus = can.interface.Bus(channel=iface, interface="socketcan")
        except Exception as e:
            self._emit({"type": "error", "msg": f"CAN bus open failed on {iface}: {e}"})
            return

        self._connected = True
        self._port = iface
        self._protocol = "ISO 15765-4 CAN 500kbps"
        self._running = True
        self._start_time = time.monotonic()
        self._sample_count = 0

        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(DB_PATH)
        _init_db(db)
        cur = db.execute(
            "INSERT INTO sessions (started_at, port, protocol) VALUES (?,?,?)",
            (datetime.now().isoformat(), iface, self._protocol),
        )
        db.commit()
        self._session_id = cur.lastrowid

        csv_path = CSV_DIR / f"session_{self._session_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        csv_file = open(csv_path, "w", newline="")
        fieldnames = [
            "ts", "elapsed_s", "rpm", "coolant_c", "maf_gs",
            "throttle_pct", "map_kpa", "iat_c", "speed_kph",
            "stft_pct", "ltft_pct", "timing_deg", "o2_b1s1_v", "o2_b1s2_v",
            "anomaly_flag", "anomaly_reason",
        ]
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        self._emit({"type": "status", **self.status()})

        try:
            while self._running:
                ts = datetime.now().isoformat()
                elapsed = round(time.monotonic() - self._start_time, 2)
                row: dict = {"ts": ts, "elapsed_s": elapsed}

                for key, (pid,) in CAN_PIDS.items():
                    val = self._query_pid(bus, pid)
                    row[key] = round(val, 3) if val is not None else None

                flag, reason = _detect_anomaly(row)
                row["anomaly_flag"] = flag
                row["anomaly_reason"] = reason

                db.execute("""
                    INSERT INTO readings (
                        session_id, ts, elapsed_s, rpm, coolant_c, maf_gs,
                        throttle_pct, map_kpa, iat_c, speed_kph, stft_pct, ltft_pct,
                        timing_deg, o2_b1s1_v, o2_b1s2_v, anomaly_flag, anomaly_reason
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    self._session_id, ts, elapsed,
                    row.get("rpm"), row.get("coolant_c"), row.get("maf_gs"),
                    row.get("throttle_pct"), row.get("map_kpa"), row.get("iat_c"),
                    row.get("speed_kph"), row.get("stft_pct"), row.get("ltft_pct"),
                    row.get("timing_deg"), row.get("o2_b1s1_v"), row.get("o2_b1s2_v"),
                    flag, reason,
                ))
                db.commit()
                writer.writerow({k: row.get(k, "") for k in fieldnames})
                csv_file.flush()

                self._sample_count += 1
                row["type"] = "reading"
                row["sample_count"] = self._sample_count
                self._emit(row)

                time.sleep(1.0)

        finally:
            bus.shutdown()
            csv_file.close()
            db.close()
            self._connected = False
            self._running = False
            self._emit({
                "type": "status",
                "connected": False,
                "logging": False,
                "session_id": self._session_id,
            })

    def _query_pid(self, bus, pid: int) -> Optional[float]:
        """Send OBD2 Mode 01 single-frame request, return decoded value or None."""
        import can
        req = can.Message(
            arbitration_id=0x7DF,
            data=[0x02, 0x01, pid, 0x00, 0x00, 0x00, 0x00, 0x00],
            is_extended_id=False,
        )
        try:
            bus.send(req)
            deadline = time.monotonic() + 0.5
            while time.monotonic() < deadline:
                msg = bus.recv(timeout=0.05)
                if msg is None:
                    continue
                # ECU responses are 0x7E8–0x7EF
                if 0x7E8 <= msg.arbitration_id <= 0x7EF:
                    d = msg.data
                    if len(d) >= 4 and d[1] == 0x41 and d[2] == pid:
                        return _decode_pid(pid, d[3:])
        except Exception:
            pass
        return None

    @staticmethod
    def _find_can_interface() -> Optional[str]:
        """Return the first live SocketCAN interface name."""
        net = Path("/sys/class/net")
        for name in ("slcan0", "can0", "slcan1", "can1"):
            if (net / name).exists():
                return name
        return None

    @staticmethod
    def _decode_dtc(high: int, low: int) -> str:
        system = ("P", "C", "B", "U")[(high >> 6) & 0x03]
        d1 = (high >> 4) & 0x03
        d2 = high & 0x0F
        d3 = (low >> 4) & 0x0F
        d4 = low & 0x0F
        return f"{system}{d1}{d2:X}{d3:X}{d4:X}"

    def _read_dtc_mode(self, bus, mode: int) -> list[str]:
        """Read DTCs for one OBD2 service mode (0x03, 0x07, or 0x0A)."""
        import can
        response_mode = mode + 0x40
        try:
            bus.send(can.Message(
                arbitration_id=0x7DF,
                data=[0x01, mode, 0, 0, 0, 0, 0, 0],
                is_extended_id=False,
            ))
        except Exception:
            return []

        payload: Optional[bytearray] = None
        deadline = time.monotonic() + 2.0

        while time.monotonic() < deadline:
            msg = bus.recv(timeout=0.15)
            if msg is None:
                continue
            if not (0x7E8 <= msg.arbitration_id <= 0x7EF):
                continue
            d = msg.data
            pci = d[0] & 0xF0

            if pci == 0x00:  # Single frame
                data_len = d[0] & 0x0F
                if data_len < 2 or d[1] != response_mode:
                    continue
                payload = bytearray(d[2:1 + data_len])
                break

            elif pci == 0x10:  # First frame — multi-frame response
                total_len = ((d[0] & 0x0F) << 8) | d[1]
                if d[2] != response_mode:
                    continue
                ecu_id = msg.arbitration_id - 8  # 0x7E8 -> 0x7E0
                payload = bytearray(d[3:8])       # 5 bytes after service ID
                remaining = total_len - 1 - 5     # subtract service ID + first 5 bytes

                try:
                    bus.send(can.Message(
                        arbitration_id=ecu_id,
                        data=[0x30, 0, 0, 0, 0, 0, 0, 0],
                        is_extended_id=False,
                    ))
                except Exception:
                    break

                seq = 1
                cf_deadline = time.monotonic() + 2.0
                while remaining > 0 and time.monotonic() < cf_deadline:
                    cf = bus.recv(timeout=0.2)
                    if cf is None:
                        continue
                    if not (0x7E8 <= cf.arbitration_id <= 0x7EF):
                        continue
                    if (cf.data[0] & 0xF0) != 0x20:
                        continue
                    if (cf.data[0] & 0x0F) != (seq % 16):
                        break
                    take = min(7, remaining)
                    payload.extend(cf.data[1:1 + take])
                    remaining -= take
                    seq += 1
                break

        if not payload:
            return []

        num_dtcs = payload[0]
        dtcs: list[str] = []
        for i in range(num_dtcs):
            off = 1 + i * 2
            if off + 1 >= len(payload):
                break
            h, lo = payload[off], payload[off + 1]
            if h == 0 and lo == 0:
                continue
            dtcs.append(self._decode_dtc(h, lo))
        return dtcs

    def read_dtcs(self) -> dict:
        try:
            import can
        except ImportError:
            return {"error": "python-can not installed"}

        iface = self._find_can_interface()
        if not iface:
            return {"error": "No CAN interface — adapter not connected"}

        try:
            bus = can.interface.Bus(channel=iface, interface="socketcan")
        except Exception as e:
            return {"error": f"CAN open failed: {e}"}

        try:
            current   = self._read_dtc_mode(bus, 0x03)
            time.sleep(0.15)
            pending   = self._read_dtc_mode(bus, 0x07)
            time.sleep(0.15)
            permanent = self._read_dtc_mode(bus, 0x0A)

            def annotate(codes: list[str]) -> list[dict]:
                return [{"code": c, "description": DTC_DESCRIPTIONS.get(c, "Unknown code")} for c in codes]

            return {
                "current":   annotate(current),
                "pending":   annotate(pending),
                "permanent": annotate(permanent),
            }
        finally:
            bus.shutdown()

    def clear_dtcs(self) -> dict:
        try:
            import can
        except ImportError:
            return {"ok": False, "error": "python-can not installed"}

        iface = self._find_can_interface()
        if not iface:
            return {"ok": False, "error": "No CAN interface — adapter not connected"}

        try:
            bus = can.interface.Bus(channel=iface, interface="socketcan")
        except Exception as e:
            return {"ok": False, "error": f"CAN open failed: {e}"}

        try:
            bus.send(can.Message(
                arbitration_id=0x7DF,
                data=[0x01, 0x04, 0, 0, 0, 0, 0, 0],
                is_extended_id=False,
            ))
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                msg = bus.recv(timeout=0.2)
                if msg is None:
                    continue
                if 0x7E8 <= msg.arbitration_id <= 0x7EF and (msg.data[1] == 0x44):
                    return {"ok": True}
            return {"ok": False, "error": "No clear confirmation from ECU"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
        finally:
            bus.shutdown()

    def _emit(self, data: dict) -> None:
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._put_nowait, data)

    def _put_nowait(self, data: dict) -> None:
        try:
            self.data_queue.put_nowait(data)
        except asyncio.QueueFull:
            try:
                self.data_queue.get_nowait()
                self.data_queue.put_nowait(data)
            except Exception:
                pass
