"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import { WS_URL, type LoggerStatus, type Reading } from "@/lib/api";

export interface OBDStreamState {
  connected: boolean;
  status: LoggerStatus | null;
  latest: Reading | null;
  history: Reading[];      // rolling 120-sample window
  anomalyReason: string;
}

const MAX_HISTORY = 120;

export function useOBDStream(): OBDStreamState {
  const ws = useRef<WebSocket | null>(null);
  const [state, setState] = useState<OBDStreamState>({
    connected: false,
    status: null,
    latest: null,
    history: [],
    anomalyReason: "",
  });

  const connect = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN) return;

    const socket = new WebSocket(WS_URL);

    socket.onopen = () => {
      setState(prev => ({ ...prev, connected: true }));
      // send keep-alive pings every 20 s
      const ping = setInterval(() => {
        if (socket.readyState === WebSocket.OPEN) socket.send("ping");
        else clearInterval(ping);
      }, 20_000);
    };

    socket.onclose = () => {
      setState(prev => ({ ...prev, connected: false }));
      // reconnect after 3 s
      setTimeout(connect, 3000);
    };

    socket.onerror = () => socket.close();

    socket.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data as string);
        if (msg.type === "reading") {
          const r = msg as Reading & { type: string; sample_count: number };
          setState(prev => ({
            ...prev,
            latest: r,
            history: [...prev.history.slice(-(MAX_HISTORY - 1)), r],
            anomalyReason: r.anomaly_flag ? (r.anomaly_reason ?? "") : prev.anomalyReason,
          }));
        } else if (msg.type === "status" || msg.type === "heartbeat") {
          setState(prev => ({ ...prev, status: msg as LoggerStatus }));
        } else if (msg.type === "error") {
          console.error("OBD error:", msg.msg);
        }
      } catch (_) {}
    };

    ws.current = socket;
  }, []);

  useEffect(() => {
    connect();
    return () => {
      ws.current?.close();
    };
  }, [connect]);

  return state;
}
