#!/usr/bin/env python3
"""
============================================================
Mini Cooper R56 N14 - Step 4: Log Analysis
Verified for: RPi5, Ubuntu 24.04 LTS arm64
============================================================
Usage:
    python ~/mini_obd/scripts/04_analyse.py          # latest
    python ~/mini_obd/scripts/04_analyse.py --list
    python ~/mini_obd/scripts/04_analyse.py --session 3
    python ~/mini_obd/scripts/04_analyse.py --idle-only
============================================================
"""

import sqlite3
import argparse
import os
import sys
from pathlib import Path
from datetime import datetime

try:
    import pandas as pd
    import matplotlib
    # Non-interactive backend - works headless on Ubuntu Server
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    import numpy as np
except ImportError as e:
    print(f"Missing library: {e}")
    print("Run: pip install pandas matplotlib numpy")
    sys.exit(1)

# ── Config (runtime home detection for Ubuntu 24.04) ─────────
HOME    = str(Path.home())
DB_PATH = f"{HOME}/mini_obd/data/mini_obd.db"
LOG_DIR = f"{HOME}/mini_obd/logs"

# N14 reference ranges
N14 = {
    "maf_idle"  : (1.5, 6.0),
    "ltft_norm" : (-10, 10),
    "stft_norm" : (-10, 10),
    "coolant"   : (75, 110),
}

# Colours
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"

def ok(m):   print(f"  {GREEN}✓{RESET} {m}")
def err(m):  print(f"  {RED}✗{RESET} {m}")
def warn(m): print(f"  {YELLOW}!{RESET} {m}")

# ── Session helpers ───────────────────────────────────────────
def list_sessions(conn):
    df = pd.read_sql("""
        SELECT
            session_id,
            started_at,
            port,
            protocol,
            ROUND((JULIANDAY('now') - JULIANDAY(started_at)) * 86400) AS duration_s
        FROM sessions
        ORDER BY session_id DESC
    """, conn)
    if df.empty:
        print("No sessions logged yet.")
    else:
        print("\nLogged Sessions:")
        print(df.to_string(index=False))

def load_session(conn, session_id=None, idle_only=False):
    if session_id is None:
        cur = conn.cursor()
        cur.execute("SELECT MAX(session_id) FROM sessions")
        row = cur.fetchone()
        if not row or row[0] is None:
            print("No sessions in database — run the logger first.")
            sys.exit(1)
        session_id = row[0]

    print(f"Loading session {session_id}...")
    df = pd.read_sql(
        "SELECT * FROM readings WHERE session_id=? ORDER BY elapsed_s",
        conn,
        params=(session_id,)
    )

    if df.empty:
        print(f"No data for session {session_id}")
        sys.exit(1)

    if idle_only:
        df = df[df["rpm"].fillna(0) < 1100]
        print(f"  Idle filter (<1100 RPM): {len(df)} samples")

    print(f"  {len(df)} samples, "
          f"{df['elapsed_s'].max():.1f}s duration")
    return df, session_id

# ── Diagnostic summary ────────────────────────────────────────
def print_summary(df):
    print(f"\n{'='*55}")
    print(" N14 Diagnostic Summary")
    print(f"{'='*55}")

    cols = {
        "maf_gs"     : ("MAF (g/s)",           None),
        "stft_pct"   : ("Short Fuel Trim (%)",  (-10, 10)),
        "ltft_pct"   : ("Long Fuel Trim (%)",   (-10, 10)),
        "rpm"        : ("RPM",                  None),
        "coolant_c"  : ("Coolant Temp (°C)",    (75, 110)),
        "iat_c"      : ("IAT (°C)",             None),
        "engine_load": ("Engine Load (%)",       None),
        "map_kpa"    : ("MAP (kPa)",            None),
    }

    for col, (label, limits) in cols.items():
        if col in df.columns and df[col].notna().any():
            s    = df[col].dropna()
            mean = s.mean()
            line = (f"  {label:<25} "
                    f"min={s.min():7.2f}  "
                    f"mean={mean:7.2f}  "
                    f"max={s.max():7.2f}")
            if limits and not (limits[0] <= mean <= limits[1]):
                print(f"{RED}{line}  ← OUTSIDE NORMAL{RESET}")
            else:
                print(line)

    # Anomaly count
    if "anomaly_flag" in df.columns:
        n   = int(df["anomaly_flag"].sum())
        tot = len(df)
        pct = 100 * n / tot if tot else 0
        print(f"\n  Anomaly flags: {n}/{tot} ({pct:.1f}%)")
        if n > 0:
            top = df[df["anomaly_flag"]==1]["anomaly_reason"].value_counts()
            for reason, count in top.head(5).items():
                print(f"    [{count:>4}x] {reason}")

    # LTFT diagnosis
    if "ltft_pct" in df.columns and df["ltft_pct"].notna().any():
        ltft = df["ltft_pct"].mean()
        stft = df["stft_pct"].mean() if "stft_pct" in df.columns else 0
        combined = ltft + stft
        print(f"\n  ── Fuel Trim Diagnosis ──")
        print(f"  LTFT mean : {ltft:+.1f}%")
        print(f"  STFT mean : {stft:+.1f}%")
        print(f"  Combined  : {combined:+.1f}%")

        if ltft > 15:
            err(f"LTFT {ltft:+.1f}% — SEVERELY LEAN")
            err("DME at correction limit → DME code 2B5F expected")
            warn("Causes: MAF signal low, air leak after MAF, PCV fault")
        elif ltft > 10:
            warn(f"LTFT {ltft:+.1f}% — Running lean")
            warn("MAF likely reading below actual airflow")
        elif ltft < -10:
            warn(f"LTFT {ltft:+.1f}% — Running rich")
            warn("MAF may be reading high / fuel pressure high")
        else:
            ok(f"LTFT {ltft:+.1f}% — Within normal range")
            if abs(ltft) > 5:
                warn("Borderline — monitor over multiple drive cycles")

# ── Plots ─────────────────────────────────────────────────────
def plot_session(df, session_id, output_dir):
    fig = plt.figure(figsize=(14, 10))
    fig.suptitle(
        f"Mini R56 N14 — OBD Session {session_id}   "
        f"({datetime.now().strftime('%Y-%m-%d')})\n"
        f"P0100 / DME 2B5 MAF Diagnostic Analysis",
        fontsize=12, fontweight='bold'
    )

    gs = gridspec.GridSpec(3, 2, figure=fig, hspace=0.45, wspace=0.3)
    t  = df["elapsed_s"]

    # Plot 1 — MAF over time (full width)
    ax1 = fig.add_subplot(gs[0, :])
    if "maf_gs" in df.columns and df["maf_gs"].notna().any():
        ax1.plot(t, df["maf_gs"], color="steelblue",
                 lw=1.2, label="MAF (g/s)")
        ax1.axhspan(*N14["maf_idle"], alpha=0.15, color="green",
                    label=f"Idle normal {N14['maf_idle']} g/s")
        anomalies = df[df["anomaly_flag"] == 1] \
                    if "anomaly_flag" in df.columns else df.iloc[:0]
        if not anomalies.empty and "maf_gs" in anomalies.columns:
            ax1.scatter(anomalies["elapsed_s"], anomalies["maf_gs"],
                        color="red", s=18, zorder=5,
                        label="Anomaly", alpha=0.7)
    ax1.set_title("Mass Air Flow — Primary P0100 Diagnostic")
    ax1.set_ylabel("MAF (g/s)")
    ax1.legend(fontsize=8)
    ax1.grid(True, alpha=0.3)

    # Plot 2 — Fuel trims
    ax2 = fig.add_subplot(gs[1, 0])
    for col, color, label in [
        ("stft_pct", "orange", "STFT (%)"),
        ("ltft_pct", "red",    "LTFT (%)"),
    ]:
        if col in df.columns and df[col].notna().any():
            ax2.plot(t, df[col], color=color, lw=1.2,
                     label=label, alpha=0.85)
    ax2.axhspan(*N14["ltft_norm"], alpha=0.1, color="green",
                label="Normal ±10%")
    ax2.axhline(0, color="gray", lw=0.8, ls="--")
    ax2.set_title("Fuel Trims (STFT / LTFT)")
    ax2.set_ylabel("Trim (%)")
    ax2.legend(fontsize=8)
    ax2.grid(True, alpha=0.3)

    # Plot 3 — RPM
    ax3 = fig.add_subplot(gs[1, 1])
    if "rpm" in df.columns and df["rpm"].notna().any():
        ax3.plot(t, df["rpm"], color="purple", lw=1.0)
        ax3.axhline(1100, color="gray", ls="--", lw=0.8,
                    label="Idle threshold")
    ax3.set_title("Engine RPM")
    ax3.set_ylabel("RPM")
    ax3.legend(fontsize=8)
    ax3.grid(True, alpha=0.3)

    # Plot 4 — MAF vs RPM scatter (colour = LTFT)
    ax4 = fig.add_subplot(gs[2, 0])
    if all(c in df.columns for c in ("rpm", "maf_gs")):
        mask = df["rpm"].notna() & df["maf_gs"].notna()
        c_data = df.loc[mask, "ltft_pct"] \
                 if "ltft_pct" in df.columns else "steelblue"
        sc = ax4.scatter(
            df.loc[mask, "rpm"],
            df.loc[mask, "maf_gs"],
            c=c_data if isinstance(c_data, str) else c_data.values,
            cmap="RdYlGn_r", alpha=0.5, s=8,
            vmin=-20, vmax=20
        )
        if not isinstance(c_data, str):
            plt.colorbar(sc, ax=ax4, label="LTFT (%)")
    ax4.set_xlabel("RPM")
    ax4.set_ylabel("MAF (g/s)")
    ax4.set_title("MAF vs RPM  (colour = LTFT)")
    ax4.grid(True, alpha=0.3)

    # Plot 5 — Temperatures
    ax5 = fig.add_subplot(gs[2, 1])
    for col, color, label in [
        ("coolant_c", "red",  "Coolant (°C)"),
        ("iat_c",     "blue", "IAT (°C)"),
    ]:
        if col in df.columns and df[col].notna().any():
            ax5.plot(t, df[col], color=color, lw=1.2, label=label)
    ax5.set_title("Engine Temperatures")
    ax5.set_ylabel("Temp (°C)")
    ax5.legend(fontsize=8)
    ax5.grid(True, alpha=0.3)

    for ax in (ax1, ax2, ax3, ax5):
        ax.set_xlabel("Elapsed Time (s)")
    ax4.set_xlabel("RPM")

    # Save — Agg backend writes PNG without display
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    out = os.path.join(output_dir, f"analysis_session_{session_id}.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    ok(f"Plot saved: {out}")
    print(f"\n  Copy to laptop:")
    print(f"  scp {os.getenv('USER', 'ubuntu')}@<PI-IP>:{out} ./")
    return out

# ── Entry Point ───────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Mini R56 N14 OBD Log Analyser"
    )
    parser.add_argument("--session",   type=int, default=None)
    parser.add_argument("--list",      action="store_true")
    parser.add_argument("--idle-only", action="store_true",
                        dest="idle_only")
    args = parser.parse_args()

    if not os.path.exists(DB_PATH):
        print(f"Database not found: {DB_PATH}")
        print("Run the logger first.")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)

    if args.list:
        list_sessions(conn)
        conn.close()
        sys.exit(0)

    df, sid = load_session(conn, args.session, args.idle_only)
    print_summary(df)
    plot_session(df, sid, LOG_DIR)
    conn.close()
    print()
