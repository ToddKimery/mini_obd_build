"use client";
import { createContext, useContext, useEffect, useState } from "react";

type TempUnit = "F" | "C";

interface Settings {
  tempUnit: TempUnit;
  setTempUnit: (u: TempUnit) => void;
}

const SettingsContext = createContext<Settings>({
  tempUnit: "F",
  setTempUnit: () => {},
});

export function SettingsProvider({ children }: { children: React.ReactNode }) {
  const [tempUnit, setTempUnitState] = useState<TempUnit>("F");

  useEffect(() => {
    const stored = localStorage.getItem("tempUnit");
    if (stored === "C" || stored === "F") setTempUnitState(stored);
  }, []);

  const setTempUnit = (u: TempUnit) => {
    setTempUnitState(u);
    localStorage.setItem("tempUnit", u);
  };

  return (
    <SettingsContext.Provider value={{ tempUnit, setTempUnit }}>
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings() {
  return useContext(SettingsContext);
}

export function toDisplayTemp(celsius: number | null | undefined, unit: TempUnit): number | null {
  if (celsius == null) return null;
  return unit === "F" ? Math.round((celsius * 9) / 5 + 32) : Math.round(celsius);
}
