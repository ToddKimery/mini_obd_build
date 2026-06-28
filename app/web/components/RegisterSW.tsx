"use client";
import { useEffect } from "react";
import { API } from "@/lib/api";

export function RegisterSW() {
  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(console.error);
    }
    // Sync Pi clock to phone time every time the app loads.
    // Fire-and-forget — silently ignored if Pi is offline or in dev.
    API.syncTime().catch(() => undefined);
  }, []);
  return null;
}
