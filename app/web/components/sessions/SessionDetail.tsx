"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { API, type SessionDetail as TSessionDetail } from "@/lib/api";
import { SessionCache } from "@/lib/sessionCache";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { DiagnosticReport } from "@/components/sessions/DiagnosticReport";
import { AIReport } from "@/components/sessions/AIReport";

function fmtDate(s: string) {
  return new Date(s).toLocaleString(undefined, {
    month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

export function SessionDetail({ sessionId }: { sessionId: number }) {
  const [detail, setDetail] = useState<TSessionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [fromCache, setFromCache] = useState(false);
  const [plotOpen, setPlotOpen] = useState(false);

  useEffect(() => {
    API.session(sessionId)
      .then(data => {
        SessionCache.saveDetail(sessionId, data);
        setDetail(data);
        setFromCache(false);
      })
      .catch(() => {
        const cached = SessionCache.loadDetail(sessionId);
        if (cached) {
          setDetail(cached);
          setFromCache(true);
        }
      })
      .finally(() => setLoading(false));
  }, [sessionId]);

  if (loading) return <p className="text-slate-500 text-sm">Loading…</p>;
  if (!detail) return <p className="text-slate-500 text-sm">Session not found.</p>;

  const { session, readings } = detail;
  const anomalies = readings.filter((r) => r.anomaly_flag);
  const mafValues = readings.map((r) => r.maf_gs).filter((v) => v != null) as number[];
  const ltftValues = readings.map((r) => r.ltft_pct).filter((v) => v != null) as number[];
  const avg = (arr: number[]) => arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : null;
  const avgMaf = avg(mafValues);
  const avgLtft = avg(ltftValues);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold text-slate-100">Session {session.session_id}</h1>
          <p className="text-sm text-slate-400">{fmtDate(session.started_at)}</p>
          {session.protocol && (
            <p className="text-xs text-slate-500 mt-0.5">{session.protocol}</p>
          )}
        </div>
        <Link href="/sessions/">
          <Button variant="outline" size="sm" className="border-slate-700 text-slate-400">
            ← Back
          </Button>
        </Link>
      </div>

      {fromCache && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-amber-950/50 border border-amber-800/60 text-amber-300 text-xs">
          <span className="shrink-0">⚡</span>
          <span>Pi offline — showing locally cached data</span>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 text-sm">
        <div className="bg-slate-800 rounded-lg p-3 border border-slate-700">
          <p className="text-slate-400 text-xs uppercase tracking-wide mb-1">Samples</p>
          <p className="text-slate-100 font-semibold">{readings.length}</p>
        </div>
        <div className="bg-slate-800 rounded-lg p-3 border border-slate-700">
          <p className="text-slate-400 text-xs uppercase tracking-wide mb-1">Anomalies</p>
          <p className={anomalies.length ? "text-red-400 font-semibold" : "text-emerald-400 font-semibold"}>
            {anomalies.length}
          </p>
        </div>
        <div className="bg-slate-800 rounded-lg p-3 border border-slate-700">
          <p className="text-slate-400 text-xs uppercase tracking-wide mb-1">Avg MAF</p>
          <p className="text-slate-100 font-semibold">
            {avgMaf != null ? `${avgMaf.toFixed(2)} g/s` : "—"}
          </p>
        </div>
        <div className="bg-slate-800 rounded-lg p-3 border border-slate-700">
          <p className="text-slate-400 text-xs uppercase tracking-wide mb-1">Avg LTFT</p>
          <p className={Math.abs(avgLtft ?? 0) > 10 ? "text-red-400 font-semibold" : "text-slate-100 font-semibold"}>
            {avgLtft != null ? `${avgLtft.toFixed(1)}%` : "—"}
          </p>
        </div>
      </div>

      {/* Diagnostic report */}
      <div>
        <p className="text-xs text-slate-500 uppercase tracking-wide mb-3">Diagnostic Report</p>
        <DiagnosticReport sessionId={sessionId} piOffline={fromCache} />
      </div>

      {/* AI Analysis */}
      <div>
        <p className="text-xs text-slate-500 uppercase tracking-wide mb-3">AI Analysis</p>
        <AIReport sessionId={sessionId} piOffline={fromCache} />
      </div>

      {!fromCache && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs text-slate-500 uppercase tracking-wide">Analysis Plot</p>
            <button
              onClick={() => setPlotOpen(true)}
              className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
            >
              expand ↗
            </button>
          </div>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={API.plotUrl(sessionId)}
            alt={`Session ${sessionId} plot`}
            className="w-full rounded-lg border border-slate-700 cursor-pointer"
            onClick={() => setPlotOpen(true)}
            onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
          />
        </div>
      )}

      <Modal
        open={plotOpen}
        onClose={() => setPlotOpen(false)}
        title={`Session ${sessionId} — Analysis Plot`}
        className="max-w-3xl"
      >
        <div className="overflow-auto px-2 pb-4" style={{ maxHeight: "80vh" }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={API.plotUrl(sessionId)}
            alt={`Session ${sessionId} plot`}
            className="w-full rounded-lg"
            style={{ minWidth: "600px" }}
          />
        </div>
      </Modal>

      {anomalies.length > 0 && (
        <div>
          <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Anomaly Log</p>
          <div className="flex flex-col gap-1.5 max-h-64 overflow-y-auto">
            {anomalies.map((r) => (
              <div key={r.id} className="bg-red-950/40 border border-red-900/50 rounded px-3 py-2 text-xs">
                <span className="text-slate-400">{r.elapsed_s.toFixed(1)}s</span>
                {" — "}
                <span className="text-red-300">{r.anomaly_reason}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
