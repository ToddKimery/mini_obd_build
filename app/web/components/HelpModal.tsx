"use client";
import { Modal } from "@/components/ui/modal";

interface Props {
  open: boolean;
  onClose: () => void;
}

function H(props: { children: React.ReactNode }) {
  return (
    <p className="text-xs text-slate-500 uppercase tracking-wide mt-6 mb-2 first:mt-0">
      {props.children}
    </p>
  );
}

function Step({ n, children }: { n: number; children: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <span className="shrink-0 w-5 h-5 rounded-full bg-emerald-800 text-emerald-200 text-xs font-bold flex items-center justify-center mt-0.5">
        {n}
      </span>
      <p className="text-sm text-slate-300 leading-snug">{children}</p>
    </div>
  );
}

type Level = "ok" | "warn" | "crit";
function Row({ pid, idle, load, concern, level = "ok" }: {
  pid: string; idle: string; load: string; concern: string; level?: Level;
}) {
  const dot = level === "ok" ? "bg-emerald-500" : level === "warn" ? "bg-amber-400" : "bg-red-500";
  return (
    <tr className="border-t border-slate-800">
      <td className="py-2 pr-3 text-slate-200 text-xs font-medium whitespace-nowrap">
        <span className={`inline-block w-1.5 h-1.5 rounded-full mr-1.5 ${dot} align-middle`} />
        {pid}
      </td>
      <td className="py-2 pr-3 text-slate-400 text-xs">{idle}</td>
      <td className="py-2 pr-3 text-slate-400 text-xs">{load}</td>
      <td className="py-2 text-slate-500 text-xs">{concern}</td>
    </tr>
  );
}

export function HelpModal({ open, onClose }: Props) {
  return (
    <Modal open={open} onClose={onClose} title="Guide — R56 N14" className="max-w-lg">
      <div className="overflow-y-auto max-h-[80vh] px-4 pb-5 flex flex-col gap-1 text-slate-300">

        {/* ── Protocol ── */}
        <H>Session protocol</H>
        <div className="flex flex-col gap-3">
          <Step n={1}>
            Plug ELM327 adapter into the OBD-II port (under the dash, driver side).
            Turn ignition to <strong className="text-slate-200">ON</strong> or start the engine.
          </Step>
          <Step n={2}>
            Connect your phone to the <strong className="text-slate-200">mini-obd</strong> WiFi
            network, then open the app. The Live page should show a green "Connected" dot in the
            logger control.
          </Step>
          <Step n={3}>
            <strong className="text-slate-200">Session 1 — warm idle.</strong> Cold-start, tap
            Start, let the engine idle until coolant is stable at operating temp
            (185–210°F / 87–99°C). Minimum 5 minutes. This captures open-loop → closed-loop
            transition and lets LTFT settle.
          </Step>
          <Step n={4}>
            <strong className="text-slate-200">Session 2 — drive.</strong> 15–20 minutes. Include:
            slow city cruise, a couple of moderate pulls to 4 000 RPM, one highway WOT pull
            (3rd or 4th gear, 2 500 → 5 500 RPM), and a coast/decel section. Tap Stop when done.
          </Step>
          <Step n={5}>
            Open the Sessions tab, select your session, and review the Diagnostic Report. The
            AI Analysis can summarize findings and suggest next steps.
          </Step>
        </div>

        {/* ── PID table ── */}
        <H>PID reference — N14 warm engine</H>
        <p className="text-xs text-slate-500 mb-2">Imperial units shown. Switch in Settings.</p>
        <div className="overflow-x-auto -mx-1">
          <table className="w-full text-left min-w-[420px]">
            <thead>
              <tr>
                <th className="pb-1 pr-3 text-xs text-slate-600 font-normal">PID</th>
                <th className="pb-1 pr-3 text-xs text-slate-600 font-normal">Warm idle</th>
                <th className="pb-1 pr-3 text-xs text-slate-600 font-normal">Cruise / boost</th>
                <th className="pb-1 text-xs text-slate-600 font-normal">Flag if…</th>
              </tr>
            </thead>
            <tbody>
              <Row
                pid="MAF g/s"
                idle="2–4"
                load="8–15 cruise · 30–60+ WOT"
                concern="< 1.5 at idle or flat during WOT"
                level="crit"
              />
              <Row
                pid="LTFT %"
                idle="−5 to +5"
                load="−10 to +10"
                concern="> +10% sustained = lean / MAF under-reads"
                level="crit"
              />
              <Row
                pid="STFT %"
                idle="oscillating ±5"
                load="oscillating ±5"
                concern="flatlined or > ±15"
                level="warn"
              />
              <Row
                pid="RPM"
                idle="700–850"
                load="varies"
                concern="< 600 hunting, or > 1 100 when warm"
              />
              <Row
                pid="Coolant °F"
                idle="220–228"
                load="220–228"
                concern="> 240°F overheating"
                level="crit"
              />
              <Row
                pid="IAT °F"
                idle="ambient + 10–30"
                load="varies with boost"
                concern="> 160°F — heat soak affecting charge"
                level="warn"
              />
              <Row
                pid="MAP (vacuum)"
                idle="−14 to −20 inHg"
                load="approaches 0 under load"
                concern="< −10 inHg at idle = vacuum leak"
                level="warn"
              />
              <Row
                pid="MAP (boost)"
                idle="—"
                load="8–14 PSI at WOT"
                concern="< 6 PSI at WOT = boost leak / turbo"
                level="warn"
              />
              <Row
                pid="Throttle %"
                idle="0–2"
                load="10–40 cruise · 85–100 WOT"
                concern="never reaches 85%+ at WOT = sensor"
              />
              <Row
                pid="Timing °"
                idle="8–15 BTDC"
                load="20–30 BTDC"
                concern="heavy retard under boost = knock"
                level="warn"
              />
              <Row
                pid="O2 B1S1 V"
                idle="0.1–0.9 switching"
                load="varies"
                concern="flatlined high or low = sensor fault"
                level="warn"
              />
              <Row
                pid="O2 B1S2 V"
                idle="0.5–0.8 steady"
                load="0.5–0.8 steady"
                concern="switching like B1S1 = failing cat"
                level="warn"
              />
            </tbody>
          </table>
        </div>

        {/* ── What good looks like ── */}
        <H>What a healthy session looks like</H>
        <ul className="flex flex-col gap-2 pl-1">
          {[
            "Coolant climbs smoothly from cold to 220–228°F and holds steady. N14 runs hot by design — this is normal.",
            "STFT oscillates ±5% throughout — the O2 sensor is driving closed-loop control.",
            "LTFT settles within ±5% after the engine is fully warm.",
            "MAF rises predictably with RPM and throttle. A WOT pull shows a sharp, clean spike to 30 g/s+.",
            "Vacuum at idle is deep (−15 inHg or more). Boost on a WOT pull reaches 8 PSI+.",
            "Timing advances cleanly with load and retreats only briefly if the tune requests it — no sustained retard.",
            "O2 B1S1 switches actively; B1S2 is lazy and steady.",
          ].map((t, i) => (
            <li key={i} className="flex gap-2 text-sm text-slate-400 leading-snug">
              <span className="text-emerald-600 mt-0.5 shrink-0">—</span>
              {t}
            </li>
          ))}
        </ul>

        {/* ── MAF fault context ── */}
        <H>N14 MAF / P0100 — what to look for</H>
        <div className="flex flex-col gap-2">
          {[
            { label: "MAF under-reading", text: "LTFT climbs positive (ECU adding fuel) while MAF looks low for the RPM. Classic dirty or failing MAF element. Clean with MAF cleaner; if it returns, replace." },
            { label: "Vacuum leak", text: "STFT and LTFT both lean. Idle vacuum shallow (< −10 inHg). RPM may hunt. Air entering after the MAF bypasses the fuel calculation." },
            { label: "Boost leak", text: "LTFT lean only under load. MAP boost pressure low. Listen for hiss on WOT pull. Common after top-end work — check intercooler pipes and charge pipe clamps." },
            { label: "Intake re-seal", text: "After a top-end rebuild, any intake manifold or throttle body gasket that is even slightly off will cause unmetered air. Check idle vacuum first — if it is weak, suspect here before the MAF sensor itself." },
          ].map(({ label, text }) => (
            <div key={label} className="rounded-lg bg-slate-800/60 border border-slate-700 px-3 py-2">
              <p className="text-xs font-semibold text-slate-200 mb-0.5">{label}</p>
              <p className="text-xs text-slate-400 leading-relaxed">{text}</p>
            </div>
          ))}
        </div>

      </div>
    </Modal>
  );
}
