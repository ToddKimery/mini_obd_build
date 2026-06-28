"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { API, type SessionSummary } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

function fmtDate(s: string) {
  return new Date(s).toLocaleString(undefined, {
    month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function fmtDuration(s: number | null) {
  if (s == null) return "—";
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`;
}

export function SessionList() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    API.sessions()
      .then(setSessions)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-slate-500 text-sm">Loading sessions…</p>;
  if (!sessions.length) return <p className="text-slate-500 text-sm">No sessions recorded yet.</p>;

  return (
    <div className="flex flex-col gap-3">
      {sessions.map((s) => (
        <Link key={s.session_id} href={`/sessions/?id=${s.session_id}`}>
          <Card className="bg-slate-800 border-slate-700 hover:border-slate-500 transition-colors cursor-pointer">
            <CardContent className="px-4 py-3 flex items-center justify-between gap-4">
              <div>
                <p className="text-slate-200 text-sm font-medium">
                  Session {s.session_id} &nbsp;
                  <span className="text-slate-400 font-normal">{fmtDate(s.started_at)}</span>
                </p>
                <p className="text-slate-500 text-xs mt-0.5">
                  {s.sample_count} samples · {fmtDuration(s.duration_s)}
                  {s.port ? ` · ${s.port}` : ""}
                </p>
              </div>
              <div className="flex gap-2 shrink-0">
                {s.anomaly_count > 0 && (
                  <Badge variant="destructive" className="text-xs">
                    {s.anomaly_count} anomaly{s.anomaly_count !== 1 ? "s" : ""}
                  </Badge>
                )}
                {s.anomaly_count === 0 && (
                  <Badge variant="outline" className="border-emerald-700 text-emerald-400 text-xs">
                    clean
                  </Badge>
                )}
              </div>
            </CardContent>
          </Card>
        </Link>
      ))}
    </div>
  );
}
