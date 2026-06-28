const BASE =
  typeof window !== "undefined"
    ? `${window.location.protocol}//${window.location.host}`
    : "http://192.168.4.1:8080";

export const WS_URL =
  typeof window !== "undefined"
    ? `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws`
    : "ws://192.168.4.1:8080/ws";

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, options);
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

export interface LoggerStatus {
  connected: boolean;
  logging: boolean;
  session_id: number | null;
  port: string | null;
  protocol: string | null;
  sample_count: number;
  elapsed_s: number;
}

export interface SessionSummary {
  session_id: number;
  started_at: string;
  port: string | null;
  protocol: string | null;
  sample_count: number;
  duration_s: number | null;
  anomaly_count: number;
}

export interface Reading {
  id: number;
  session_id: number;
  ts: string;
  elapsed_s: number;
  rpm: number | null;
  coolant_c: number | null;
  maf_gs: number | null;
  throttle_pct: number | null;
  map_kpa: number | null;
  iat_c: number | null;
  speed_kph: number | null;
  stft_pct: number | null;
  ltft_pct: number | null;
  timing_deg: number | null;
  o2_b1s1_v: number | null;
  o2_b1s2_v: number | null;
  anomaly_flag: number;
  anomaly_reason: string;
}

export interface SessionDetail {
  session: {
    session_id: number;
    started_at: string;
    port: string;
    protocol: string;
    notes: string | null;
  };
  readings: Reading[];
}

export interface ReportFinding {
  level: "critical" | "warning" | "ok";
  tag: string;
  text: string;
}

export interface DiagnosticReport {
  session_id: number;
  started_at: string;
  duration_s: number;
  sample_count: number;
  idle_samples: number;
  anomaly_count: number;
  anomaly_pct: number;
  metrics: {
    maf: { idle_avg: number | null; idle_min: number | null; idle_max: number | null; all_max: number | null };
    ltft: { avg: number | null; peak: number | null; threshold_crossed_at_s: number | null };
    stft: { avg: number | null };
    combined_ft_peak: number | null;
    coolant: { min: number | null; max: number | null };
    o2_b1s1_stddev: number | null;
  };
  findings: ReportFinding[];
  conclusion: {
    status: "critical" | "warning" | "ok" | "inconclusive";
    fault: string | null;
    confidence: "high" | "medium" | "low";
    summary: string;
    likely_causes: string[];
    next_steps: string[];
  };
}

export const API = {
  status:       ()                    => api<LoggerStatus>("/api/status"),
  start:        (port?: string)       => api<{ ok: boolean }>("/api/logger/start", {
    method: "POST",
    ...(port ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify({ port }) } : {}),
  }),
  stop:         ()                    => api<{ ok: boolean; session_id: number }>("/api/logger/stop", { method: "POST" }),
  sessions:     ()                    => api<SessionSummary[]>("/api/sessions"),
  session:      (id: number)          => api<SessionDetail>(`/api/sessions/${id}`),
  report:       (id: number)          => api<DiagnosticReport>(`/api/sessions/${id}/report`),
  plotUrl:      (id: number)          => `${BASE}/api/sessions/${id}/plot`,
};
