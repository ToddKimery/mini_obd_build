"use client";
import { useEffect, useRef, useState } from "react";
import { API, type APIKeyStatus } from "@/lib/api";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { useSettings } from "@/lib/settings";
import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  onClose: () => void;
}

type UpdatePhase = "idle" | "running" | "restarting" | "done";

export function SettingsModal({ open, onClose }: Props) {
  const { tempUnit, setTempUnit } = useSettings();

  const [status, setStatus] = useState<APIKeyStatus | null>(null);
  const [keyInput, setKeyInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const [updatePhase, setUpdatePhase] = useState<UpdatePhase>("idle");
  const [logLines, setLogLines] = useState<string[]>([]);
  const [version, setVersion] = useState<{ version: string; date: string } | null>(null);
  const logRef = useRef<HTMLPreElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (open) {
      setKeyInput("");
      setSaveMsg(null);
      API.apiKeyStatus().then(setStatus).catch(() => setStatus(null));
      API.version().then(setVersion).catch(() => setVersion({ version: "dev", date: "" }));
    } else {
      // Clean up polling when modal closes
      if (pollRef.current) clearInterval(pollRef.current);
    }
  }, [open]);

  // Auto-scroll log to bottom when new lines arrive
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [logLines]);

  async function startUpdate() {
    setUpdatePhase("running");
    setLogLines(["Starting update..."]);
    try {
      await API.forceUpdate();
    } catch {
      setLogLines(prev => [...prev, "Failed to reach Pi."]);
      setUpdatePhase("idle");
      return;
    }

    // Poll the update log every 1.5s
    pollRef.current = setInterval(async () => {
      try {
        const data = await API.updateLog();
        setLogLines(data.lines.length ? data.lines : ["Waiting for output..."]);

        // Detect completion: last log line says "Update complete" or "Done" or "skipping"
        const last = data.lines[data.lines.length - 1] ?? "";
        if (/complete|Done|skipping/i.test(last)) {
          clearInterval(pollRef.current!);
          setUpdatePhase("done");
        }
      } catch {
        // API unreachable — service is restarting
        setUpdatePhase("restarting");
        clearInterval(pollRef.current!);

        // Wait for it to come back
        const waitInterval = setInterval(async () => {
          try {
            await API.updateLog();
            clearInterval(waitInterval);
            setLogLines(prev => [...prev, "Service back online."]);
            setUpdatePhase("done");
          } catch { /* still restarting */ }
        }, 2000);
      }
    }, 1500);
  }

  async function saveKey() {
    if (!keyInput.trim()) return;
    setSaving(true);
    setSaveMsg(null);
    try {
      await API.setApiKey(keyInput.trim());
      setSaveMsg({ ok: true, text: "Key saved — AI analysis is ready." });
      setKeyInput("");
      const s = await API.apiKeyStatus();
      setStatus(s);
    } catch {
      setSaveMsg({ ok: false, text: "Failed to save key. Check Pi connection." });
    }
    setSaving(false);
  }

  async function removeKey() {
    setSaving(true);
    setSaveMsg(null);
    try {
      await API.setApiKey("");
      setSaveMsg({ ok: true, text: "Key removed." });
      const s = await API.apiKeyStatus();
      setStatus(s);
    } catch {
      setSaveMsg({ ok: false, text: "Failed to remove key." });
    }
    setSaving(false);
  }

  return (
    <Modal open={open} onClose={onClose} title="Settings" className="max-w-sm">
      <div className="flex flex-col gap-6 px-1 pb-2">

        {/* ── Temperature unit ── */}
        <div>
          <p className="text-xs text-slate-500 uppercase tracking-wide mb-3">Temperature Unit</p>
          <div className="flex rounded-lg overflow-hidden border border-slate-700 w-fit">
            <button
              onClick={() => setTempUnit("F")}
              className={cn(
                "px-5 py-2 text-sm font-medium transition-colors",
                tempUnit === "F"
                  ? "bg-emerald-700 text-white"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
              )}
            >
              °F
            </button>
            <button
              onClick={() => setTempUnit("C")}
              className={cn(
                "px-5 py-2 text-sm font-medium transition-colors",
                tempUnit === "C"
                  ? "bg-emerald-700 text-white"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
              )}
            >
              °C
            </button>
          </div>
        </div>

        {/* ── Anthropic API Key ── */}
        <div>
          <p className="text-xs text-slate-500 uppercase tracking-wide mb-1">Anthropic API Key</p>
          <p className="text-xs text-slate-600 mb-3">
            Required for AI session analysis. Stored on the Pi only — never leaves the device.
          </p>

          {/* Status badge */}
          <div className="flex items-center gap-2 mb-4">
            <div className={cn(
              "w-2 h-2 rounded-full shrink-0",
              status?.configured ? "bg-emerald-500" : "bg-slate-600"
            )} />
            <span className="text-sm text-slate-300">
              {status == null
                ? "Checking…"
                : status.configured
                  ? `Configured${status.source === "env" ? " (environment variable)" : " (saved on Pi)"}`
                  : "Not configured"}
            </span>
          </div>

          {/* Key input */}
          <div className="flex flex-col gap-2">
            <input
              type="password"
              value={keyInput}
              onChange={e => setKeyInput(e.target.value)}
              onKeyDown={e => e.key === "Enter" && saveKey()}
              placeholder="sk-ant-api03-…"
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-emerald-600 transition-colors font-mono"
            />
            <div className="flex gap-2">
              <Button
                onClick={saveKey}
                disabled={saving || !keyInput.trim()}
                className="flex-1 bg-emerald-700 hover:bg-emerald-600 text-white text-sm"
              >
                {saving ? "Saving…" : "Save Key"}
              </Button>
              {status?.configured && status.source === "file" && (
                <Button
                  onClick={removeKey}
                  disabled={saving}
                  variant="outline"
                  className="border-red-800 text-red-400 hover:bg-red-950/40 text-sm"
                >
                  Remove
                </Button>
              )}
            </div>
          </div>

          {saveMsg && (
            <p className={cn(
              "text-xs mt-2",
              saveMsg.ok ? "text-emerald-400" : "text-red-400"
            )}>
              {saveMsg.text}
            </p>
          )}
        </div>

        {/* ── Force Update ── */}
        <div>
          <div className="flex items-baseline justify-between mb-1">
            <p className="text-xs text-slate-500 uppercase tracking-wide">Software Update</p>
            {version && (
              <span className="text-xs font-mono text-slate-600">
                {version.version}{version.date ? ` · ${version.date}` : ""}
              </span>
            )}
          </div>
          <p className="text-xs text-slate-600 mb-3">
            Pulls latest code from GitHub, rebuilds, and restarts the service.
          </p>

          {updatePhase === "idle" && (
            <Button
              onClick={startUpdate}
              variant="outline"
              className="w-full border-sky-800 text-sky-400 hover:bg-sky-950/40"
            >
              Force Update from GitHub
            </Button>
          )}

          {updatePhase !== "idle" && (
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2 mb-1">
                {updatePhase === "running" && (
                  <span className="h-2 w-2 rounded-full bg-sky-400 animate-pulse shrink-0" />
                )}
                {updatePhase === "restarting" && (
                  <span className="h-2 w-2 rounded-full bg-amber-400 animate-pulse shrink-0" />
                )}
                {updatePhase === "done" && (
                  <span className="h-2 w-2 rounded-full bg-emerald-400 shrink-0" />
                )}
                <span className="text-xs text-slate-400">
                  {updatePhase === "running"    && "Updating…"}
                  {updatePhase === "restarting" && "Service restarting…"}
                  {updatePhase === "done"       && "Update complete"}
                </span>
              </div>

              <pre
                ref={logRef}
                className="bg-slate-950 border border-slate-800 rounded-lg p-3 text-xs text-slate-400 font-mono overflow-y-auto max-h-48 whitespace-pre-wrap"
              >
                {logLines.join("\n")}
              </pre>

              {updatePhase === "done" && (
                <Button
                  onClick={() => { setUpdatePhase("idle"); setLogLines([]); }}
                  variant="outline"
                  size="sm"
                  className="border-slate-700 text-slate-400 w-full"
                >
                  Dismiss
                </Button>
              )}
            </div>
          )}
        </div>

      </div>
    </Modal>
  );
}
