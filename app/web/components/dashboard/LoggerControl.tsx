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

  const handleStart = async () => {
    setBusy(true);
    try { await API.start(); } catch (e) { console.error(e); }
    setBusy(false);
  };

  const handleStop = async () => {
    setBusy(true);
    try { await API.stop(); } catch (e) { console.error(e); }
    setBusy(false);
  };

  const isLogging = status?.logging ?? false;

  return (
    <div className="flex items-center gap-3 flex-wrap">
      {/* Connection indicator */}
      <div className="flex items-center gap-1.5">
        <span
          className={cn(
            "h-2 w-2 rounded-full",
            wsConnected ? "bg-emerald-400 animate-pulse" : "bg-slate-600"
          )}
        />
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
          Session {status?.session_id} &nbsp;·&nbsp; {status?.sample_count} samples
        </Badge>
      )}

      {!isLogging ? (
        <Button
          size="sm"
          onClick={handleStart}
          disabled={busy}
          className="bg-emerald-600 hover:bg-emerald-500 text-white"
        >
          {busy ? "Starting…" : "Start Logging"}
        </Button>
      ) : (
        <Button
          size="sm"
          variant="destructive"
          onClick={handleStop}
          disabled={busy}
        >
          {busy ? "Stopping…" : "Stop"}
        </Button>
      )}
    </div>
  );
}
