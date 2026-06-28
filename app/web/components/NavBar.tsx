"use client";
import Link from "next/link";
import { useSettings } from "@/lib/settings";
import { cn } from "@/lib/utils";

export function NavBar() {
  const { tempUnit, setTempUnit } = useSettings();

  return (
    <header className="sticky top-0 z-10 bg-slate-900/80 backdrop-blur border-b border-slate-800 px-4 py-3 flex items-center justify-between">
      <Link href="/" className="font-semibold text-slate-100 tracking-tight">
        Mini OBD <span className="text-slate-500 font-normal text-sm">R56 N14</span>
      </Link>

      <div className="flex items-center gap-4">
        {/* Temp unit toggle */}
        <div className="flex rounded-md overflow-hidden border border-slate-700 text-xs">
          <button
            onClick={() => setTempUnit("F")}
            className={cn(
              "px-2.5 py-1 transition-colors",
              tempUnit === "F"
                ? "bg-slate-600 text-slate-100"
                : "text-slate-500 hover:text-slate-300"
            )}
          >
            °F
          </button>
          <button
            onClick={() => setTempUnit("C")}
            className={cn(
              "px-2.5 py-1 transition-colors",
              tempUnit === "C"
                ? "bg-slate-600 text-slate-100"
                : "text-slate-500 hover:text-slate-300"
            )}
          >
            °C
          </button>
        </div>

        <nav className="flex gap-4 text-sm">
          <Link href="/" className="text-slate-400 hover:text-slate-100 transition-colors">Live</Link>
          <Link href="/sessions/" className="text-slate-400 hover:text-slate-100 transition-colors">Sessions</Link>
        </nav>
      </div>
    </header>
  );
}
