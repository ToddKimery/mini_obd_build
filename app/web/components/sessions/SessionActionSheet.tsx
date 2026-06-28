"use client";
import { useEffect, useState } from "react";
import { API, type SessionSummary } from "@/lib/api";
import { cn } from "@/lib/utils";

function fmtDate(s: string) {
  return new Date(s).toLocaleString(undefined, {
    month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

interface Props {
  session: SessionSummary;
  onClose: () => void;
  onLockToggle: (id: number, locked: boolean) => void;
  onDeleted: (id: number) => void;
}

export function SessionActionSheet({ session, onClose, onLockToggle, onDeleted }: Props) {
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  // Reset confirm state if sheet re-opens for a different session
  useEffect(() => { setConfirmDelete(false); }, [session.session_id]);

  // Auto-reset confirm after 3 s of inaction
  useEffect(() => {
    if (!confirmDelete) return;
    const t = setTimeout(() => setConfirmDelete(false), 3000);
    return () => clearTimeout(t);
  }, [confirmDelete]);

  async function handleLock() {
    setBusy(true);
    try {
      const newLocked = !session.locked;
      await API.lockSession(session.session_id, newLocked);
      onLockToggle(session.session_id, newLocked);
      onClose();
    } catch { /* ignore */ }
    setBusy(false);
  }

  async function handleDelete() {
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    setBusy(true);
    try {
      await API.deleteSession(session.session_id);
      onDeleted(session.session_id);
      onClose();
    } catch { /* locked or not found */ }
    setBusy(false);
  }

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/60"
        onClick={onClose}
      />

      {/* Sheet */}
      <div className="fixed inset-x-0 bottom-0 z-50 bg-slate-900 rounded-t-2xl border-t border-slate-700">
        {/* Drag handle */}
        <div className="flex justify-center pt-3 pb-1">
          <div className="w-10 h-1 rounded-full bg-slate-700" />
        </div>

        {/* Session header */}
        <div className="px-5 py-3 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <p className="text-slate-200 font-medium">
              Session {session.session_id}
            </p>
            {session.locked ? (
              <span className="text-xs text-amber-400 border border-amber-700 rounded px-1.5 py-0.5">
                locked
              </span>
            ) : null}
          </div>
          <p className="text-slate-500 text-sm mt-0.5">{fmtDate(session.started_at)}</p>
          <p className="text-slate-600 text-xs mt-0.5">
            {session.sample_count} samples
            {session.anomaly_count > 0 ? ` · ${session.anomaly_count} anomalies` : ""}
          </p>
        </div>

        {/* Actions */}
        <div className="flex flex-col">
          {/* Lock / Unlock */}
          <button
            onClick={handleLock}
            disabled={busy}
            className="flex items-center gap-4 px-5 py-4 text-slate-200 active:bg-slate-800 transition-colors"
          >
            {session.locked ? (
              /* unlock icon */
              <svg className="w-5 h-5 text-amber-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                <path d="M7 11V7a5 5 0 0 1 9.9-1" />
              </svg>
            ) : (
              /* lock icon */
              <svg className="w-5 h-5 text-slate-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                <path d="M7 11V7a5 5 0 0 1 10 0v4" />
              </svg>
            )}
            <span className="text-sm">
              {session.locked ? "Unlock Session" : "Lock Session"}
            </span>
          </button>

          <div className="h-px bg-slate-800 mx-5" />

          {/* Delete */}
          <button
            onClick={handleDelete}
            disabled={busy || !!session.locked}
            className={cn(
              "flex items-center gap-4 px-5 py-4 transition-colors",
              session.locked
                ? "text-slate-600"
                : confirmDelete
                  ? "text-red-300 active:bg-red-950/30"
                  : "text-red-400 active:bg-slate-800"
            )}
          >
            <svg className="w-5 h-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <polyline points="3 6 5 6 21 6" />
              <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
              <path d="M10 11v6M14 11v6" />
              <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
            </svg>
            <span className="text-sm">
              {session.locked
                ? "Locked — cannot delete"
                : confirmDelete
                  ? "Tap again to confirm delete"
                  : "Delete Session"}
            </span>
          </button>
        </div>

        {/* Cancel */}
        <div className="h-px bg-slate-800" />
        <button
          onClick={onClose}
          className="w-full py-4 text-slate-400 text-sm font-medium active:bg-slate-800 transition-colors"
        >
          Cancel
        </button>

        {/* iOS safe area spacer */}
        <div className="h-safe-bottom" />
      </div>
    </>
  );
}
