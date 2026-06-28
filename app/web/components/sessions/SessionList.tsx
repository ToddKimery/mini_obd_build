"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { API, type SessionSummary } from "@/lib/api";
import { SessionCache } from "@/lib/sessionCache";
import { useLongPress } from "@/hooks/useLongPress";
import { SessionActionSheet } from "./SessionActionSheet";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

function fmtDate(s: string) {
  return new Date(s).toLocaleString(undefined, {
    month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

function fmtDuration(s: number | null) {
  if (s == null) return "—";
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`;
}

function SessionCard({
  session,
  onLongPress,
  onNavigate,
}: {
  session: SessionSummary;
  onLongPress: () => void;
  onNavigate: () => void;
}) {
  const { pressProps, didFire } = useLongPress(onLongPress);

  return (
    <div
      {...pressProps}
      onClick={() => { if (!didFire()) onNavigate(); }}
      className="cursor-pointer select-none"
    >
      <Card className={`border-slate-700 transition-colors hover:border-slate-500 ${
        session.locked ? "bg-slate-800/60" : "bg-slate-800"
      }`}>
        <CardContent className="px-4 py-3 flex items-center justify-between gap-4">
          <div className="min-w-0">
            <p className="text-slate-200 text-sm font-medium flex items-center gap-1.5 flex-wrap">
              Session {session.session_id}
              {session.locked ? (
                <svg className="w-3 h-3 text-amber-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                  <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                </svg>
              ) : null}
              <span className="text-slate-400 font-normal">{fmtDate(session.started_at)}</span>
            </p>
            <p className="text-slate-500 text-xs mt-0.5 truncate">
              {session.sample_count} samples · {fmtDuration(session.duration_s)}
              {session.port ? ` · ${session.port}` : ""}
            </p>
          </div>
          <div className="flex gap-2 shrink-0">
            {session.anomaly_count > 0 && (
              <Badge variant="destructive" className="text-xs">
                {session.anomaly_count} anomaly{session.anomaly_count !== 1 ? "s" : ""}
              </Badge>
            )}
            {session.anomaly_count === 0 && (
              <Badge variant="outline" className="border-emerald-700 text-emerald-400 text-xs">
                clean
              </Badge>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export function SessionList() {
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [fromCache, setFromCache] = useState(false);
  const [activeSession, setActiveSession] = useState<SessionSummary | null>(null);

  useEffect(() => {
    API.sessions()
      .then(data => {
        SessionCache.saveSessionList(data);
        setSessions(data);
        setFromCache(false);
      })
      .catch(() => {
        const cached = SessionCache.loadSessionList();
        if (cached) { setSessions(cached); setFromCache(true); }
      })
      .finally(() => setLoading(false));
  }, []);

  function handleLockToggle(id: number, locked: boolean) {
    setSessions(prev =>
      prev.map(s => s.session_id === id ? { ...s, locked: locked ? 1 : 0 } : s)
    );
  }

  function handleDeleted(id: number) {
    setSessions(prev => prev.filter(s => s.session_id !== id));
  }

  if (loading) return <p className="text-slate-500 text-sm">Loading sessions…</p>;

  return (
    <>
      <div className="flex flex-col gap-3">
        {fromCache && (
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-amber-950/50 border border-amber-800/60 text-amber-300 text-xs">
            <span className="shrink-0">⚡</span>
            <span>Pi offline — showing last {sessions.length} cached session{sessions.length !== 1 ? "s" : ""}</span>
          </div>
        )}

        {sessions.length === 0 && (
          <p className="text-slate-500 text-sm">No sessions recorded yet.</p>
        )}

        {sessions.map(s => (
          <SessionCard
            key={s.session_id}
            session={s}
            onLongPress={() => setActiveSession(s)}
            onNavigate={() => router.push(`/sessions/?id=${s.session_id}`)}
          />
        ))}

        {!fromCache && sessions.length > 0 && (
          <p className="text-center text-xs text-slate-700 mt-1">
            Hold a session to lock or delete
          </p>
        )}
      </div>

      {activeSession && (
        <SessionActionSheet
          session={activeSession}
          onClose={() => setActiveSession(null)}
          onLockToggle={handleLockToggle}
          onDeleted={handleDeleted}
        />
      )}
    </>
  );
}
