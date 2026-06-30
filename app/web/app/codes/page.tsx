"use client";
import { useState, useCallback } from "react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

interface DtcEntry {
  code: string;
  description: string;
}

interface DtcResult {
  current: DtcEntry[];
  pending: DtcEntry[];
  permanent: DtcEntry[];
}

const SYSTEM_LABEL: Record<string, string> = { P: "Powertrain", C: "Chassis", B: "Body", U: "Network" };
const SYSTEM_CLASS: Record<string, string> = {
  P: "border-red-700 text-red-300",
  C: "border-amber-700 text-amber-300",
  B: "border-blue-700 text-blue-300",
  U: "border-purple-700 text-purple-300",
};

function DtcCard({ entry, accent }: { entry: DtcEntry; accent: string }) {
  const sys = entry.code[0];
  return (
    <div className={cn("rounded-lg border p-3 bg-slate-800/60 flex items-start gap-3", accent)}>
      <div className="flex flex-col gap-1.5 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-mono font-bold text-slate-100">{entry.code}</span>
          <Badge variant="outline" className={cn("text-xs", SYSTEM_CLASS[sys] ?? "border-slate-600 text-slate-400")}>
            {SYSTEM_LABEL[sys] ?? sys}
          </Badge>
        </div>
        <p className="text-xs text-slate-400 leading-snug">{entry.description}</p>
      </div>
    </div>
  );
}

function Section({
  title, dot, codes, accent, emptyMsg,
}: {
  title: string; dot: string; codes: DtcEntry[]; accent: string; emptyMsg: string;
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span className={cn("h-2 w-2 rounded-full flex-shrink-0", codes.length ? dot : "bg-slate-600")} />
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wide">{title}</h2>
        <span className="text-xs text-slate-500 ml-1">({codes.length})</span>
      </div>
      {codes.length === 0 ? (
        <p className="text-xs text-slate-500 pl-4">{emptyMsg}</p>
      ) : (
        <div className="flex flex-col gap-2">
          {codes.map(e => <DtcCard key={e.code} entry={e} accent={accent} />)}
        </div>
      )}
    </div>
  );
}

function ConfirmDialog({ onConfirm, onCancel }: { onConfirm: () => void; onCancel: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 pb-6 px-4 sm:items-center sm:pb-0">
      <div className="w-full max-w-sm rounded-xl border border-slate-700 bg-slate-900 p-5 flex flex-col gap-4">
        <h3 className="font-semibold text-slate-100">Clear all fault codes?</h3>
        <p className="text-sm text-slate-400">
          Sends OBD2 Mode 04 to the ECU. All stored and pending codes are erased and the check engine
          light turns off. Codes will return on the next drive cycle if the fault is still present.
        </p>
        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            className="h-9 rounded-md px-4 text-sm font-medium border border-slate-600 text-slate-300 hover:bg-slate-800"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="h-9 rounded-md px-4 text-sm font-medium bg-red-700 hover:bg-red-600 text-white"
          >
            Clear Codes
          </button>
        </div>
      </div>
    </div>
  );
}

export default function CodesPage() {
  const [result, setResult]           = useState<DtcResult | null>(null);
  const [loading, setLoading]         = useState(false);
  const [clearing, setClearing]       = useState(false);
  const [error, setError]             = useState<string | null>(null);
  const [cleared, setCleared]         = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const readCodes = useCallback(async () => {
    setLoading(true);
    setError(null);
    setCleared(false);
    try {
      const r = await fetch("/api/dtc");
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        setError(d.detail ?? `Error ${r.status}`);
        return;
      }
      setResult(await r.json());
    } catch {
      setError("Network error — is the adapter connected?");
    } finally {
      setLoading(false);
    }
  }, []);

  const clearCodes = useCallback(async () => {
    setClearing(true);
    setConfirmOpen(false);
    setError(null);
    try {
      const r = await fetch("/api/dtc/clear", { method: "POST" });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        setError(d.detail ?? `Error ${r.status}`);
        return;
      }
      setResult(null);
      setCleared(true);
    } catch {
      setError("Network error");
    } finally {
      setClearing(false);
    }
  }, []);

  const total = result ? result.current.length + result.pending.length + result.permanent.length : 0;
  const milOn = result ? result.current.length > 0 : null;

  return (
    <div className="flex flex-col gap-5">
      {/* Header row */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-slate-100">Fault Codes</h1>
          {milOn !== null && (
            <Badge
              variant="outline"
              className={milOn
                ? "border-red-600 text-red-400 bg-red-950/30"
                : "border-emerald-700 text-emerald-400 bg-emerald-950/20"}
            >
              {milOn ? "MIL ON" : "MIL OFF"}
            </Badge>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={readCodes}
            disabled={loading || clearing}
            className="h-9 rounded-md px-3 text-sm font-medium bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-50"
          >
            {loading ? "Reading…" : result ? "Refresh" : "Read Codes"}
          </button>
          {result && total > 0 && (
            <button
              onClick={() => setConfirmOpen(true)}
              disabled={clearing || loading}
              className="h-9 rounded-md px-3 text-sm font-medium border border-red-700 text-red-400 hover:bg-red-950/40 disabled:opacity-50"
            >
              {clearing ? "Clearing…" : "Clear All"}
            </button>
          )}
        </div>
      </div>

      {/* Feedback banners */}
      {error && (
        <div className="rounded-lg border border-red-700 bg-red-950/30 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}
      {cleared && (
        <div className="rounded-lg border border-emerald-700 bg-emerald-950/30 px-4 py-3 text-sm text-emerald-300">
          Codes cleared. Tap Refresh to confirm the ECU has no remaining faults.
        </div>
      )}

      {/* Empty / prompt state */}
      {!result && !loading && !error && !cleared && (
        <div className="rounded-lg border border-slate-700 bg-slate-800/40 px-4 py-10 text-center">
          <p className="text-sm text-slate-400">Tap Read Codes to query the ECU.</p>
          <p className="text-xs text-slate-500 mt-1">Engine on and adapter connected required.</p>
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="flex flex-col gap-5">
          <Section
            title="Current Codes"
            dot="bg-red-500"
            codes={result.current}
            accent="border-red-800"
            emptyMsg="No confirmed codes stored"
          />
          <div className="h-px bg-slate-800" />
          <Section
            title="Pending Codes"
            dot="bg-amber-500"
            codes={result.pending}
            accent="border-amber-800"
            emptyMsg="No pending codes"
          />
          <div className="h-px bg-slate-800" />
          <Section
            title="Permanent Codes"
            dot="bg-orange-500"
            codes={result.permanent}
            accent="border-orange-800"
            emptyMsg="None — or ECU does not support Mode 0A"
          />
        </div>
      )}

      {confirmOpen && (
        <ConfirmDialog onConfirm={clearCodes} onCancel={() => setConfirmOpen(false)} />
      )}
    </div>
  );
}
