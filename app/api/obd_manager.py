"""
OBD connection manager — runs the read loop in a background thread,
puts each sample into an asyncio Queue for WebSocket broadcasting,
and writes to SQLite (same schema as scripts/03_obd_logger.py).
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

try:
    import obd
    OBD_AVAILABLE = True
except ImportError:
    OBD_AVAILABLE = False

# ── Thresholds (must match 03_obd_logger.py) ─────────────────────────────────
THRESHOLDS = {
    "maf_gs":       {"min": 0.5,  "max": 25.0},
    "ltft_pct":     {"min": -15,  "max": 15},
    "combined_ft":  {"min": -20,  "max": 20},
    "coolant_c":    {"min": 70,   "max": 115},
}

# ── PID map ───────────────────────────────────────────────────────────────────
PID_MAP = {
    "rpm":         obd.commands.RPM         if OBD_AVAILABLE else None,
    "coolant_c":   obd.commands.COOLANT_TEMP if OBD_AVAILABLE else None,
    "maf_gs":      obd.commands.MAF         if OBD_AVAILABLE else None,
    "throttle_pct":obd.commands.THROTTLE_POS if OBD_AVAILABLE else None,
    "map_kpa":     obd.commands.INTAKE_PRESSURE if OBD_AVAILABLE else None,
    "iat_c":       obd.commands.INTAKE_TEMP if OBD_AVAILABLE else None,
    "speed_kph":   obd.commands.SPEED       if OBD_AVAILABLE else None,
    "stft_pct":    obd.commands.SHORT_FUEL_TRIM_1 if OBD_AVAILABLE else None,
    "ltft_pct":    obd.commands.LONG_FUEL_TRIM_1  if OBD_AVAILABLE else None,
    "timing_deg":  obd.commands.TIMING_ADVANCE    if OBD_AVAILABLE else None,
    "o2_b1s1_v":   obd.commands.O2_B1S1    if OBD_AVAILABLE else None,
    "o2_b1s2_v":   obd.commands.O2_B1S2    if OBD_AVAILABLE else None,
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
            if not OBD_AVAILABLE:
                return {"ok": False, "error": "obd module not installed"}
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
        port = port or self._find_port()
        if not port:
            self._emit({"type": "error", "msg": "No OBD port found"})
            return

        connection = obd.OBD(
            portstr=port,
            baudrate=38400,
            fast=False,
            timeout=10,
        )
        if not connection.is_connected():
            self._emit({"type": "error", "msg": f"Could not connect on {port}"})
            return

        self._connected = True
        self._port = port
        self._protocol = str(connection.protocol_name())
        self._running = True
        self._start_time = time.monotonic()
        self._sample_count = 0

        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(DB_PATH)
        _init_db(db)
        cur = db.execute(
            "INSERT INTO sessions (started_at, port, protocol) VALUES (?,?,?)",
            (datetime.now().isoformat(), port, self._protocol),
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

                for key, cmd in PID_MAP.items():
                    if cmd is None:
                        continue
                    resp = connection.query(cmd)
                    if resp and not resp.is_null():
                        try:
                            row[key] = round(float(resp.value.magnitude), 3)
                        except Exception:
                            row[key] = None
                    else:
                        row[key] = None

                flag, reason = _detect_anomaly(row)
                row["anomaly_flag"] = flag
                row["anomaly_reason"] = reason

                db.execute(f"""
                    INSERT INTO readings (
                        session_id, ts, elapsed_s,
                        rpm, coolant_c, maf_gs, throttle_pct, map_kpa, iat_c,
                        speed_kph, stft_pct, ltft_pct, timing_deg,
                        o2_b1s1_v, o2_b1s2_v, anomaly_flag, anomaly_reason
                    ) VALUES (
                        ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                    )
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
            connection.close()
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

    def _find_port(self) -> Optional[str]:
        from pathlib import Path
        kdcan = Path("/dev/kdcan")
        if kdcan.exists():
            return str(kdcan)
        ports = obd.scan_serial()
        return ports[0] if ports else None

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
