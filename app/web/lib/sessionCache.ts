import type { SessionSummary, SessionDetail, DiagnosticReport, AIReport } from "./api";

const MAX_SESSIONS = 10;

// ── Helpers ────────────────────────────────────────────────────────────────

function lsGet<T>(key: string): T | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function lsSet(key: string, value: unknown): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // QuotaExceededError — storage full, skip silently
  }
}

function lsDel(key: string): void {
  if (typeof window === "undefined") return;
  try { localStorage.removeItem(key); } catch { /* ignore */ }
}

// ── ID tracking (ordered newest-first, max 10) ─────────────────────────────

function getCachedIds(): number[] {
  return lsGet<number[]>("obd:cached-ids") ?? [];
}

function trackId(id: number): void {
  let ids = getCachedIds().filter(x => x !== id);
  ids.unshift(id);
  if (ids.length > MAX_SESSIONS) {
    ids.slice(MAX_SESSIONS).forEach(evicted => {
      lsDel(`obd:session:${evicted}`);
      lsDel(`obd:report:${evicted}`);
      lsDel(`obd:ai:${evicted}`);
    });
    ids = ids.slice(0, MAX_SESSIONS);
  }
  lsSet("obd:cached-ids", ids);
}

// ── Public API ─────────────────────────────────────────────────────────────

export const SessionCache = {
  // ── Session list ──────────────────────────────────────────────────────────
  saveSessionList(sessions: SessionSummary[]): void {
    lsSet("obd:sessions", sessions.slice(0, MAX_SESSIONS));
  },
  loadSessionList(): SessionSummary[] | null {
    return lsGet<SessionSummary[]>("obd:sessions");
  },

  // ── Session detail ────────────────────────────────────────────────────────
  saveDetail(id: number, detail: SessionDetail): void {
    trackId(id);
    lsSet(`obd:session:${id}`, detail);
  },
  loadDetail(id: number): SessionDetail | null {
    return lsGet<SessionDetail>(`obd:session:${id}`);
  },

  // ── Diagnostic report ─────────────────────────────────────────────────────
  saveReport(id: number, report: DiagnosticReport): void {
    lsSet(`obd:report:${id}`, report);
  },
  loadReport(id: number): DiagnosticReport | null {
    return lsGet<DiagnosticReport>(`obd:report:${id}`);
  },

  // ── AI report ─────────────────────────────────────────────────────────────
  saveAiReport(id: number, report: AIReport): void {
    lsSet(`obd:ai:${id}`, report);
  },
  loadAiReport(id: number): AIReport | null {
    return lsGet<AIReport>(`obd:ai:${id}`);
  },

  /** IDs of sessions currently in local storage, newest first. */
  cachedIds(): number[] {
    return getCachedIds();
  },
};
