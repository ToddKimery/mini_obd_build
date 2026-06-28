"""
AI-powered diagnostic write-up using the Anthropic API.
Sends the rule-based report summary as context so the model
interprets actual session data, not generic OBD knowledge.

API key resolution order:
  1. ANTHROPIC_API_KEY environment variable
  2. ~/mini_obd/config/anthropic_key.txt
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional


def _load_key() -> Optional[str]:
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    key_file = Path.home() / "mini_obd" / "config" / "anthropic_key.txt"
    if key_file.exists():
        return key_file.read_text().strip() or None
    return None


def _build_prompt(rule_report: dict) -> str:
    c  = rule_report.get("conclusion", {})
    m  = rule_report.get("metrics", {})
    findings = rule_report.get("findings", [])

    maf  = m.get("maf", {})
    ltft = m.get("ltft", {})
    cool = m.get("coolant", {})

    findings_text = "\n".join(
        f"  [{f['level'].upper()}] {f['tag']}: {f['text']}"
        for f in findings
    )

    duration_m = round(rule_report.get("duration_s", 0) / 60, 1)

    return f"""You are a BMW N14 engine diagnostic specialist reviewing OBD-II data from a 2007 Mini Cooper S R56.

The vehicle recently completed a full top-end rebuild including timing chain, VANOS sprocket, cam sprocket, head gasket, pistons, and rings. It has an active P0100/2B5F MAF plausibility fault that appeared post-rebuild. DME adaptations have been reset.

## Session Data Summary

Duration: {duration_m} minutes | Samples: {rule_report.get("sample_count")} | Anomalies: {rule_report.get("anomaly_count")} ({rule_report.get("anomaly_pct")}%)

**MAF:** idle avg {maf.get("idle_avg")} g/s, min {maf.get("idle_min")} g/s, max {maf.get("idle_max")} g/s
**LTFT:** avg {ltft.get("avg")}%, peak {ltft.get("peak")}%, crossed +15% at {ltft.get("threshold_crossed_at_s")}s
**STFT:** avg {m.get("stft", {}).get("avg")}%
**Combined FT peak:** {m.get("combined_ft_peak")}%
**Coolant:** {cool.get("min")}–{cool.get("max")}°C
**O2 B1S1 activity (σ):** {m.get("o2_b1s1_stddev")}

## Rule-Based Findings
{findings_text}

## Rule-Based Conclusion
Status: {c.get("status")} | Confidence: {c.get("confidence")}
Fault: {c.get("fault")}
Summary: {c.get("summary")}

Likely causes identified:
{chr(10).join(f"  {i+1}. {cause}" for i, cause in enumerate(c.get("likely_causes", [])))}

## Your Task

Provide a detailed diagnostic write-up that:
1. Interprets what this specific data pattern tells us about the engine's condition post-rebuild
2. Explains the relationship between the MAF reading, fuel trims, O2 activity, and what it means for the N14 specifically
3. Ranks the likely root causes based on the data (not just generic possibilities) — be direct about which is most probable given a fresh rebuild
4. Identifies any additional PIDs or tests that would definitively distinguish between the top two causes
5. Notes anything in the data that is reassuring or rules out certain failure modes

Be direct and specific. This is going to a mechanic who did the rebuild themselves and understands the engine. Avoid generic OBD-101 explanations."""


def generate(rule_report: dict, model: str = "claude-sonnet-4-6") -> dict:
    key = _load_key()
    if not key:
        return {
            "error": "no_key",
            "message": "No Anthropic API key found. Set ANTHROPIC_API_KEY env var or create ~/mini_obd/config/anthropic_key.txt",
        }

    try:
        import anthropic
    except ImportError:
        return {"error": "no_package", "message": "anthropic package not installed"}

    try:
        client = anthropic.Anthropic(api_key=key)
        response = client.messages.create(
            model=model,
            max_tokens=1500,
            messages=[{"role": "user", "content": _build_prompt(rule_report)}],
        )
        return {
            "text":  response.content[0].text,
            "model": response.model,
            "input_tokens":  response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
    except anthropic.AuthenticationError:
        return {"error": "auth", "message": "Invalid API key"}
    except anthropic.APIConnectionError:
        return {"error": "offline", "message": "No internet connection — AI analysis unavailable"}
    except Exception as e:
        return {"error": "api_error", "message": str(e)}
