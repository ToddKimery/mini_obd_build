"use client";
import { createContext, useContext, useEffect, useState } from "react";

export type UnitSystem = "imperial" | "metric";

interface Settings {
  unitSystem: UnitSystem;
  setUnitSystem: (u: UnitSystem) => void;
}

const SettingsContext = createContext<Settings>({
  unitSystem: "imperial",
  setUnitSystem: () => {},
});

export function SettingsProvider({ children }: { children: React.ReactNode }) {
  const [unitSystem, setUnitSystemState] = useState<UnitSystem>("imperial");

  useEffect(() => {
    const stored = localStorage.getItem("unitSystem");
    if (stored === "imperial" || stored === "metric") setUnitSystemState(stored);
  }, []);

  const setUnitSystem = (u: UnitSystem) => {
    setUnitSystemState(u);
    localStorage.setItem("unitSystem", u);
  };

  return (
    <SettingsContext.Provider value={{ unitSystem, setUnitSystem }}>
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings() {
  return useContext(SettingsContext);
}

export function toDisplayTemp(celsius: number | null | undefined, system: UnitSystem): number | null {
  if (celsius == null) return null;
  return system === "imperial" ? Math.round((celsius * 9) / 5 + 32) : Math.round(celsius);
}

export function tempLabel(system: UnitSystem): string {
  return system === "imperial" ? "°F" : "°C";
}

// MAP is absolute kPa from OBD. Imperial: below atmospheric → inHg vacuum, above → PSI boost.
const ATM_KPA = 101.325;

export function toDisplayPressure(kpa: number | null | undefined, system: UnitSystem): { value: number | null; unit: string } {
  if (system === "metric") {
    return { value: kpa != null ? Math.round(kpa) : null, unit: "kPa" };
  }
  if (kpa == null) return { value: null, unit: "inHg" };
  const delta = kpa - ATM_KPA;
  if (delta < 0) {
    return { value: Math.round((delta / 3.38639) * 10) / 10, unit: "inHg" };
  }
  return { value: Math.round((delta / 6.89476) * 10) / 10, unit: "PSI" };
}

export function toDisplaySpeed(kph: number | null | undefined, system: UnitSystem): { value: number | null; unit: string } {
  if (kph == null) return { value: null, unit: system === "imperial" ? "mph" : "km/h" };
  return system === "imperial"
    ? { value: Math.round(kph * 0.621371), unit: "mph" }
    : { value: Math.round(kph), unit: "km/h" };
}
