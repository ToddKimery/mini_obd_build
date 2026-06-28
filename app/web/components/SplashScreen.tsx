"use client";
import { useEffect, useState } from "react";

export function SplashScreen() {
  const [phase, setPhase] = useState<"visible" | "fading" | "gone">("visible");

  useEffect(() => {
    const fadeTimer = setTimeout(() => setPhase("fading"), 700);
    const goneTimer = setTimeout(() => setPhase("gone"), 1100);
    return () => { clearTimeout(fadeTimer); clearTimeout(goneTimer); };
  }, []);

  if (phase === "gone") return null;

  return (
    <div
      id="splash-screen"
      style={{ opacity: phase === "fading" ? 0 : 1 }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/icons/launchericon-192x192.png" alt="" />
      <p className="splash-title">Mini OBD</p>
      <p className="splash-subtitle">R56 N14</p>
      <div className="splash-bar-track">
        <div className="splash-bar" />
      </div>
    </div>
  );
}
