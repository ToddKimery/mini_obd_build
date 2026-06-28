"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { API, type LoggerStatus } from "@/lib/api";
import { cn } from "@/lib/utils";

interface LoggerControlProps {
  status: LoggerStatus | null;
  wsConnected: boolean;
}

export function LoggerControl({ status, wsConnected }: LoggerControlProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleStart = async () => {
    setBusy(true);
    setError(null);
    try {
      await API.start();
    } catch (e: any) {
      setError(e?.message ?? "Failed to start");
    }
    setBusy(false);
  };

  const handleMock = async () => {
    setBusy(true);
    setError(null);
    try {
      await fetch(`${window.location.protocol}//${window.location.host}/api/logger/mock`, { method: "POST" });
    } catch (e: any) {
      setError(e?.message ?? "Failed to start mock");
    }
    setBusy(false);
  };

  const handleStop = async () => {
    setBusy(true);
    setError(null);
    try { await API.stop(); } catch (e: any) { setError(e?.message ?? "Failed to stop"); }
    setBusy(false);
  };

  const isLogging = status?.logging ?? false;

  return (
    <div className="flex flex-col items-end gap-1.5">
      <div className="flex items-center gap-3 flex-wrap justify-end">
        {/* Connection indicator */}
        <div className="flex items-center gap-1.5">
          <span className={cn(
            "h-2 w-2 rounded-full",
            wsConnected ? "bg-emerald-400 animate-pulse" : "bg-slate-600"
          )} />
          <span className="text-xs text-slate-400">
            {wsConnected ? "Connected" : "Disconnected"}
          </span>
        </div>

        {status?.protocol && (
          <Badge variant="outline" className="border-slate-600 text-slate-400 text-xs">
            {status.protocol}
          </Badge>
        )}

        {isLogging && (
          <Badge variant="outline" className="border-emerald-700 text-emerald-400 text-xs">
            Session {status?.session_id} · {status?.sample_count} samples
          </Badge>
        )}

        {!isLogging ? (
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={handleMock}
              disabled={busy}
              className="border-amber-700 text-amber-400 hover:bg-amber-950/40 text-xs"
            >
              {busy ? "Starting…" : "Demo"}
            </Button>
            <Button
              size="sm"
              onClick={handleStart}
              disabled={busy}
              className="bg-emerald-600 hover:bg-emerald-500 text-white"
            >
              {busy ? "Starting…" : "Start"}
            </Button>
          </div>
        ) : (
          <Button size="sm" variant="destructive" onClick={handleStop} disabled={busy}>
            {busy ? "Stopping…" : "Stop"}
          </Button>
        )}
      </div>

      {error && (
        <p className="text-xs text-red-400">{error}</p>
      )}
    </div>
  );
}
