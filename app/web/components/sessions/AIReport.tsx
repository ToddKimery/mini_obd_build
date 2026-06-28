"use client";
import { useEffect, useState } from "react";
import { API, type AIReport } from "@/lib/api";
import { SessionCache } from "@/lib/sessionCache";
import { Button } from "@/components/ui/button";

function fmtDate(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

type State = "loading" | "idle" | "generating" | "done";

export function AIReport({
  sessionId,
  piOffline = false,
}: {
  sessionId: number;
  piOffline?: boolean;
}) {
  const [state, setState] = useState<State>("loading");
  const [result, setResult] = useState<AIReport | null>(null);

  useEffect(() => {
    if (piOffline) {
      // Skip network — check local storage only
      const local = SessionCache.loadAiReport(sessionId);
      if (local) {
        setResult({ ...local, cached: true });
        setState("done");
      } else {
        setState("idle");
      }
      return;
    }

    // Try Pi DB first (canonical source), fall back to localStorage
    API.cachedAiReport(sessionId)
      .then(r => {
        SessionCache.saveAiReport(sessionId, r);
        setResult(r);
        setState("done");
      })
      .catch(() => {
        // 404 (no DB report) or network error — check local storage
        const local = SessionCache.loadAiReport(sessionId);
        if (local) {
          setResult({ ...local, cached: true });
          setState("done");
        } else {
          setState("idle");
        }
      });
  }, [sessionId, piOffline]);

  async function run(force = false) {
    setState("generating");
    try {
      const r = await API.aiReport(sessionId, force);
      // Save to both Pi DB (done server-side) and local storage
      SessionCache.saveAiReport(sessionId, r);
      setResult(r);
    } catch (e) {
      setResult({ error: "network", message: String(e) });
    }
    setState("done");
  }

  // ── Loading ────────────────────────────────────────────────────────────────
  if (state === "loading") {
    return <p className="text-slate-600 text-xs">Checking for saved report…</p>;
  }

  // ── No cache yet ───────────────────────────────────────────────────────────
  if (state === "idle") {
    if (piOffline) {
      return (
        <p className="text-slate-500 text-xs">AI analysis unavailable offline.</p>
      );
    }
    return (
      <Button
        onClick={() => run(false)}
        variant="outline"
        className="border-violet-700 text-violet-400 hover:bg-violet-950/40 w-full"
      >
        Run AI Analysis
      </Button>
    );
  }

  // ── Generating ─────────────────────────────────────────────────────────────
  if (state === "generating") {
    return (
      <div className="rounded-xl border border-violet-800 bg-violet-950/30 p-5 text-center">
        <p className="text-violet-300 text-sm animate-pulse">Analysing with Claude…</p>
        <p className="text-slate-500 text-xs mt-1">Usually takes 5–10 seconds</p>
      </div>
    );
  }

  // ── Done ───────────────────────────────────────────────────────────────────
  if (!result) return null;

  if (result.error) {
    return (
      <div className="flex flex-col gap-2">
        <div className="rounded-xl border border-amber-700 bg-amber-950/30 p-4">
          <p className="text-amber-300 text-sm font-medium mb-1">
            {result.error === "no_key"  ? "No API key configured" :
             result.error === "offline" ? "Offline — no internet connection" :
             result.error === "auth"    ? "Invalid API key" :
                                         "AI analysis unavailable"}
          </p>
          <p className="text-slate-400 text-xs">{result.message}</p>
          {result.error === "no_key" && (
            <p className="text-slate-500 text-xs mt-2">
              Open Settings (⚙) and paste your Anthropic API key.
            </p>
          )}
        </div>
        <Button onClick={() => setState("idle")} variant="outline" size="sm"
          className="border-slate-700 text-slate-500 w-full">
          Try Again
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-xl border border-violet-700 bg-violet-950/20 p-4">

        {/* Header */}
        <div className="flex items-start justify-between mb-3 gap-2">
          <div>
            <p className="text-xs text-violet-400 font-semibold uppercase tracking-wide">
              Claude AI Analysis
            </p>
            {result.created_at && (
              <p className="text-xs text-slate-600 mt-0.5">
                {result.cached ? "Saved" : "Generated"} {fmtDate(result.created_at)}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {result.cached && (
              <span className="text-xs text-slate-600 border border-slate-700 rounded px-1.5 py-0.5">
                cached
              </span>
            )}
            {result.model && (
              <span className="text-xs text-slate-600">{result.model}</span>
            )}
          </div>
        </div>

        {/* Body */}
        <div className="text-sm text-slate-200 leading-relaxed whitespace-pre-wrap">
          {result.text}
        </div>

        {/* Token count */}
        {result.input_tokens != null && (
          <p className="text-xs text-slate-600 mt-3 text-right">
            {result.input_tokens} in / {result.output_tokens} out tokens
          </p>
        )}
      </div>

      {/* Regenerate — only possible when Pi is online */}
      {!piOffline && (
        <Button
          onClick={() => run(true)}
          variant="outline"
          size="sm"
          className="border-violet-800 text-violet-500 hover:bg-violet-950/30 w-full"
        >
          Regenerate
        </Button>
      )}
    </div>
  );
}
