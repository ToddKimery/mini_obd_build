"use client";
import { useEffect, useState } from "react";
import { API, type DiagnosticReport, type ReportFinding } from "@/lib/api";
import { SessionCache } from "@/lib/sessionCache";
import { useSettings, tempLabel as getTempLabel } from "@/lib/settings";
import { cn } from "@/lib/utils";

function toF(c: number | null | undefined) {
  if (c == null) return null;
  return Math.round((c * 9) / 5 + 32);
}

function fmtTemp(c: number | null | undefined, unit: string) {
  if (c == null) return "—";
  const val = unit === "°F" ? toF(c) : Math.round(c);
  return `${val} ${unit}`;
}

function fmtDuration(s: number) {
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`;
}

const STATUS_STYLES = {
  critical:     "border-red-600 bg-red-950/50 text-red-300",
  warning:      "border-amber-600 bg-amber-950/50 text-amber-300",
  ok:           "border-emerald-700 bg-emerald-950/40 text-emerald-300",
  inconclusive: "border-slate-600 bg-slate-800 text-slate-400",
};

const FINDING_ICON: Record<ReportFinding["level"], string> = {
  critical: "✕",
  warning:  "!",
  ok:       "✓",
};

const FINDING_STYLES: Record<ReportFinding["level"], string> = {
  critical: "text-red-400",
  warning:  "text-amber-400",
  ok:       "text-emerald-400",
};

export function DiagnosticReport({
  sessionId,
  piOffline = false,
}: {
  sessionId: number;
  piOffline?: boolean;
}) {
  const [report, setReport] = useState<DiagnosticReport | null>(null);
  const [fromCache, setFromCache] = useState(false);
  const [loading, setLoading] = useState(true);
  const { unitSystem } = useSettings();
  const tLabel = getTempLabel(unitSystem);

  useEffect(() => {
    if (piOffline) {
      // Parent already confirmed Pi is unreachable — skip network call
      const cached = SessionCache.loadReport(sessionId);
      setReport(cached);
      setFromCache(!!cached);
      setLoading(false);
      return;
    }

    API.report(sessionId)
      .then(data => {
        SessionCache.saveReport(sessionId, data);
        setReport(data);
        setFromCache(false);
      })
      .catch(() => {
        const cached = SessionCache.loadReport(sessionId);
        setReport(cached);
        setFromCache(!!cached);
      })
      .finally(() => setLoading(false));
  }, [sessionId, piOffline]);

  if (loading) return <p className="text-slate-500 text-sm">Generating report…</p>;
  if (!report || "error" in report) {
    return (
      <p className="text-slate-500 text-sm">
        {piOffline || fromCache !== null ? "Report unavailable offline." : "Report unavailable."}
      </p>
    );
  }

  const { conclusion: c, findings, metrics: m } = report;

  return (
    <div className="flex flex-col gap-4">

      {/* ── Conclusion header ── */}
      <div className={cn("rounded-xl border p-4", STATUS_STYLES[c.status])}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-wide opacity-70 mb-0.5">
              {c.confidence} confidence
              {fromCache && <span className="ml-2 normal-case opacity-60">· cached</span>}
            </p>
            <p className="font-semibold text-base leading-snug">
              {c.fault ?? "No fault detected"}
            </p>
          </div>
          <span className={cn(
            "text-xs font-bold px-2 py-0.5 rounded-full border shrink-0",
            c.status === "critical"     && "border-red-500 text-red-400",
            c.status === "warning"      && "border-amber-500 text-amber-400",
            c.status === "ok"           && "border-emerald-600 text-emerald-400",
            c.status === "inconclusive" && "border-slate-600 text-slate-400",
          )}>
            {c.status.toUpperCase()}
          </span>
        </div>
        <p className="text-sm mt-2 opacity-90 leading-relaxed">{c.summary}</p>
      </div>

      {/* ── Key metrics row ── */}
      <div className="grid grid-cols-3 gap-2 text-center text-xs">
        {[
          { label: "Samples",     value: `${report.sample_count}` },
          { label: "Anomalies",   value: `${report.anomaly_count} (${report.anomaly_pct}%)` },
          { label: "Duration",    value: fmtDuration(report.duration_s) },
          { label: "Idle MAF avg", value: m.maf.idle_avg != null ? `${m.maf.idle_avg} g/s` : "—" },
          { label: "LTFT peak",   value: m.ltft.peak != null ? `${m.ltft.peak > 0 ? "+" : ""}${m.ltft.peak}%` : "—" },
          { label: "Combined FT", value: m.combined_ft_peak != null ? `${m.combined_ft_peak > 0 ? "+" : ""}${m.combined_ft_peak}%` : "—" },
          { label: "Coolant min", value: fmtTemp(m.coolant.min, tLabel) },
          { label: "Coolant max", value: fmtTemp(m.coolant.max, tLabel) },
          { label: "Idle samples", value: `${report.idle_samples}` },
        ].map(({ label, value }) => (
          <div key={label} className="bg-slate-800 border border-slate-700 rounded-lg px-2 py-2">
            <p className="text-slate-500 mb-0.5 leading-tight">{label}</p>
            <p className="text-slate-200 font-medium">{value}</p>
          </div>
        ))}
      </div>

      {/* ── Findings ── */}
      <div>
        <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Findings</p>
        <div className="flex flex-col gap-2">
          {findings.map((f, i) => (
            <div key={i} className="flex gap-2.5 items-start bg-slate-800/60 border border-slate-700 rounded-lg px-3 py-2.5">
              <span className={cn("font-bold text-sm shrink-0 mt-px", FINDING_STYLES[f.level])}>
                {FINDING_ICON[f.level]}
              </span>
              <div>
                <span className={cn("text-xs font-semibold mr-1.5", FINDING_STYLES[f.level])}>
                  {f.tag}
                </span>
                <span className="text-xs text-slate-300">{f.text}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Likely causes ── */}
      {c.likely_causes.length > 0 && (
        <div>
          <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Likely Causes</p>
          <ol className="flex flex-col gap-1.5">
            {c.likely_causes.map((cause, i) => (
              <li key={i} className="flex gap-2.5 text-xs text-slate-300">
                <span className="text-slate-600 shrink-0 font-mono">{i + 1}.</span>
                {cause}
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* ── Next steps ── */}
      {c.next_steps.length > 0 && (
        <div>
          <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Next Steps</p>
          <ol className="flex flex-col gap-1.5">
            {c.next_steps.map((step, i) => (
              <li key={i} className="flex gap-2.5 text-xs">
                <span className="text-slate-600 shrink-0 font-mono">{i + 1}.</span>
                <span className="text-slate-300">{step}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
