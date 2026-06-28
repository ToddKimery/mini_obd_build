"""
Rule-based diagnostic report generator for N14 OBD sessions.
All logic is deterministic — no external dependencies, runs offline.
"""
from __future__ import annotations
from typing import Optional


def _avg(vals: list[float]) -> Optional[float]:
    return round(sum(vals) / len(vals), 2) if vals else None

def _pct(part: int, total: int) -> float:
    return round(100 * part / total, 1) if total else 0.0


def generate(session: dict, readings: list[dict]) -> dict:
    """Return a structured diagnostic report dict."""

    total = len(readings)
    if total == 0:
        return {"error": "No readings in session"}

    duration_s = readings[-1].get("elapsed_s", 0)
    anomaly_count = sum(1 for r in readings if r.get("anomaly_flag"))

    # ── Idle samples (RPM < 1200) ─────────────────────────────────────────────
    idle = [r for r in readings if r.get("rpm") and r["rpm"] < 1200]

    # ── Extract signal lists ──────────────────────────────────────────────────
    maf_idle  = [r["maf_gs"]   for r in idle     if r.get("maf_gs")    is not None]
    maf_all   = [r["maf_gs"]   for r in readings  if r.get("maf_gs")    is not None]
    ltft_all  = [r["ltft_pct"] for r in readings  if r.get("ltft_pct")  is not None]
    stft_all  = [r["stft_pct"] for r in readings  if r.get("stft_pct")  is not None]
    cool_all  = [r["coolant_c"] for r in readings if r.get("coolant_c") is not None]
    rpm_all   = [r["rpm"]       for r in readings if r.get("rpm")       is not None]
    o2_all    = [r["o2_b1s1_v"] for r in readings if r.get("o2_b1s1_v") is not None]

    # ── MAF ──────────────────────────────────────────────────────────────────
    maf_idle_avg = _avg(maf_idle)
    maf_idle_min = round(min(maf_idle), 2) if maf_idle else None
    maf_idle_max = round(max(maf_idle), 2) if maf_idle else None
    maf_all_max  = round(max(maf_all),  2) if maf_all  else None

    # N14 normal idle MAF: 2.5–3.5 g/s at 820–900 RPM
    MAF_IDLE_LOW  = 1.5
    MAF_IDLE_HIGH = 6.0
    maf_deficit_pct = (
        round((2.8 - maf_idle_avg) / 2.8 * 100, 1)
        if maf_idle_avg is not None and maf_idle_avg < 2.8 else 0
    )

    # ── Fuel trims ───────────────────────────────────────────────────────────
    ltft_avg  = _avg(ltft_all)
    ltft_peak = round(max(ltft_all, key=abs), 2) if ltft_all else None
    stft_avg  = _avg(stft_all)

    combined_peaks = [
        (s + l) for s, l in zip(stft_all, ltft_all)
        if s is not None and l is not None
    ]
    combined_peak = round(max(combined_peaks, key=abs), 2) if combined_peaks else None

    # When did LTFT first exceed +15%?
    ltft_threshold_t: Optional[float] = None
    for r in readings:
        if r.get("ltft_pct") is not None and r["ltft_pct"] > 15:
            ltft_threshold_t = r.get("elapsed_s")
            break

    # ── Coolant ──────────────────────────────────────────────────────────────
    cool_min = round(min(cool_all), 1) if cool_all else None
    cool_max = round(max(cool_all), 1) if cool_all else None

    # ── O2 sensor ────────────────────────────────────────────────────────────
    o2_avg   = _avg(o2_all)
    # O2 switching: std dev of the signal (high = switching = closed loop active)
    if len(o2_all) > 1:
        mean = sum(o2_all) / len(o2_all)
        o2_stddev = round((sum((x - mean) ** 2 for x in o2_all) / len(o2_all)) ** 0.5, 3)
    else:
        o2_stddev = None

    # ── Build findings ────────────────────────────────────────────────────────
    findings: list[dict] = []

    # MAF findings
    if maf_idle_avg is not None:
        if maf_idle_avg < MAF_IDLE_LOW:
            findings.append({
                "level": "critical",
                "tag": "MAF",
                "text": (
                    f"Idle MAF avg {maf_idle_avg} g/s — {maf_deficit_pct}% below expected "
                    f"(2.5–3.5 g/s at idle). DME sees insufficient airflow signal."
                ),
            })
        elif maf_idle_avg > MAF_IDLE_HIGH:
            findings.append({
                "level": "warning",
                "tag": "MAF",
                "text": f"Idle MAF avg {maf_idle_avg} g/s — above normal idle range. Check for boost leak or MAF over-reading.",
            })
        else:
            findings.append({
                "level": "ok",
                "tag": "MAF",
                "text": f"Idle MAF avg {maf_idle_avg} g/s — within normal idle range (1.5–6.0 g/s).",
            })

    # LTFT findings
    if ltft_avg is not None:
        if abs(ltft_peak or 0) > 20:
            t_str = f" at {ltft_threshold_t:.0f}s" if ltft_threshold_t is not None else ""
            findings.append({
                "level": "critical",
                "tag": "LTFT",
                "text": (
                    f"LTFT peaked at {ltft_peak:+.1f}% (avg {ltft_avg:+.1f}%). "
                    f"Crossed +15% threshold{t_str}. DME at long-term correction limit."
                ),
            })
        elif abs(ltft_peak or 0) > 10:
            findings.append({
                "level": "warning",
                "tag": "LTFT",
                "text": f"LTFT peaked at {ltft_peak:+.1f}% (avg {ltft_avg:+.1f}%). Elevated — monitor for trend.",
            })
        else:
            findings.append({
                "level": "ok",
                "tag": "LTFT",
                "text": f"LTFT avg {ltft_avg:+.1f}%, peak {ltft_peak:+.1f}% — within normal range (±10%).",
            })

    # Combined fuel trim
    if combined_peak is not None and abs(combined_peak) > 25:
        findings.append({
            "level": "critical",
            "tag": "Combined FT",
            "text": (
                f"Combined STFT+LTFT peaked at {combined_peak:+.1f}%. "
                f"BMW 2B5F plausibility fault triggers above ~+25%."
            ),
        })

    # STFT behaviour
    if stft_avg is not None:
        if abs(stft_avg) > 8:
            findings.append({
                "level": "warning",
                "tag": "STFT",
                "text": f"STFT avg {stft_avg:+.1f}% — persistently elevated, DME adding fuel short-term.",
            })

    # Coolant
    if cool_max is not None and cool_max > 110:
        findings.append({
            "level": "critical",
            "tag": "Coolant",
            "text": f"Coolant peaked at {cool_max}°C — overheating threshold exceeded.",
        })
    elif cool_min is not None and cool_min < 70 and len(cool_all) > 60:
        findings.append({
            "level": "warning",
            "tag": "Coolant",
            "text": f"Coolant stayed below 70°C ({cool_min}°C min) — engine may not have reached operating temp.",
        })
    elif cool_min is not None:
        findings.append({
            "level": "ok",
            "tag": "Coolant",
            "text": f"Coolant {cool_min}–{cool_max}°C — normal operating range.",
        })

    # O2 activity
    if o2_stddev is not None:
        if o2_stddev > 0.08:
            findings.append({
                "level": "ok",
                "tag": "O2 B1S1",
                "text": f"O2 sensor switching actively (σ={o2_stddev}) — closed loop fuel control operating.",
            })
        elif o2_stddev < 0.03:
            findings.append({
                "level": "warning",
                "tag": "O2 B1S1",
                "text": f"O2 sensor shows minimal activity (σ={o2_stddev}) — may be running open loop or sensor lazy.",
            })

    # ── Conclusion / diagnosis ────────────────────────────────────────────────
    conclusion = _conclude(
        maf_idle_avg, maf_deficit_pct,
        ltft_avg, ltft_peak, combined_peak,
        stft_avg, cool_max,
    )

    return {
        "session_id":    session.get("session_id"),
        "started_at":    session.get("started_at"),
        "duration_s":    round(duration_s),
        "sample_count":  total,
        "idle_samples":  len(idle),
        "anomaly_count": anomaly_count,
        "anomaly_pct":   _pct(anomaly_count, total),
        "metrics": {
            "maf":  {"idle_avg": maf_idle_avg, "idle_min": maf_idle_min,
                     "idle_max": maf_idle_max, "all_max": maf_all_max},
            "ltft": {"avg": ltft_avg, "peak": ltft_peak,
                     "threshold_crossed_at_s": ltft_threshold_t},
            "stft": {"avg": stft_avg},
            "combined_ft_peak": combined_peak,
            "coolant": {"min": cool_min, "max": cool_max},
            "o2_b1s1_stddev": o2_stddev,
        },
        "findings":   findings,
        "conclusion": conclusion,
    }


def _conclude(
    maf_idle_avg, maf_deficit_pct,
    ltft_avg, ltft_peak, combined_peak,
    stft_avg, cool_max,
) -> dict:
    maf_low     = maf_idle_avg is not None and maf_idle_avg < 1.5
    maf_ok      = maf_idle_avg is not None and 1.5 <= maf_idle_avg <= 6.0
    ltft_high   = ltft_peak is not None and ltft_peak > 15
    ltft_crit   = ltft_peak is not None and ltft_peak > 20
    ft_ok       = ltft_peak is not None and abs(ltft_peak) <= 10
    combined_hi = combined_peak is not None and combined_peak > 25
    overheat    = cool_max is not None and cool_max > 110

    if overheat:
        return {
            "status":   "critical",
            "fault":    "Thermal event",
            "confidence": "high",
            "summary":  "Coolant exceeded safe operating temperature. Address cooling system before further diagnosis.",
            "likely_causes": [
                "Coolant loss or air pocket in system",
                "Thermostat stuck closed",
                "Water pump failure",
                "Head gasket compromised (cross-check for combustion gases in coolant)",
            ],
            "next_steps": [
                "Pressure test cooling system",
                "Check coolant level and condition",
                "Block tester for head gasket",
            ],
        }

    if maf_low and ltft_crit and combined_hi:
        deficit = f"{maf_deficit_pct:.0f}%" if maf_deficit_pct else "significant"
        return {
            "status":   "critical",
            "fault":    "P0100 / 2B5F — MAF Plausibility",
            "confidence": "high",
            "summary": (
                f"Classic 2B5F pattern confirmed. MAF reads {deficit} below expected at idle while RPM and MAP "
                f"are plausible. DME corrected with LTFT to {ltft_peak:+.1f}%, exceeding the plausibility "
                f"threshold and setting the fault."
            ),
            "likely_causes": [
                "Cam timing offset — exhaust cam 1+ tooth retarded reduces scavenging, DME MAP/RPM model "
                "expects more air than the (correctly reading) MAF sees",
                "MAF sensor signal fault — contaminated element, damaged wiring, poor ground",
                "Post-MAF vacuum leak — intake manifold gasket, PCV hose, boost pipes post-MAF "
                "(unmetered air enters, MAF reads low relative to actual charge)",
            ],
            "next_steps": [
                "Check cam timing marks against DME position sensor data (compare cam angle at TDC)",
                "Inspect MAF sensor element and connector — clean or replace if contaminated",
                "Smoke test intake tract from MAF to throttle body",
                "If timing confirmed correct, log MAP vs MAF vs RPM to isolate signal vs physical air fault",
            ],
        }

    if maf_ok and ltft_crit:
        return {
            "status":   "warning",
            "fault":    "High LTFT — Fuel Delivery or Vacuum Leak",
            "confidence": "medium",
            "summary": (
                f"MAF reads normally but LTFT peaked at {ltft_peak:+.1f}%. DME is adding fuel "
                f"because the engine runs lean despite correct airflow measurement. "
                f"Fault is likely post-MAF."
            ),
            "likely_causes": [
                "Vacuum/boost leak post-MAF (unmetered air causing lean condition)",
                "Fuel injector(s) underperforming — low flow or partial clog",
                "Fuel pressure low — check fuel pressure regulator and pump",
                "O2 sensor bias causing over-correction",
            ],
            "next_steps": [
                "Smoke test intake manifold and all vacuum lines",
                "Check fuel pressure at idle and under load",
                "Log injector pulse width and compare across cylinders",
            ],
        }

    if maf_ok and ft_ok:
        return {
            "status":   "ok",
            "fault":    None,
            "confidence": "high",
            "summary":  "No significant fault pattern detected. MAF and fuel trims are within normal operating range.",
            "likely_causes": [],
            "next_steps": [
                "Compare against a session captured under load or during a fault event",
                "If intermittent faults are suspected, log a longer session during the conditions that trigger them",
            ],
        }

    # Ambiguous
    return {
        "status":   "inconclusive",
        "fault":    "Insufficient data to conclude",
        "confidence": "low",
        "summary":  "The session data does not clearly match a known fault pattern. More data or a longer session may be needed.",
        "likely_causes": [],
        "next_steps": [
            "Log a session of at least 5 minutes at warm idle",
            "Capture a session that includes the conditions when the fault light appears",
        ],
    }
