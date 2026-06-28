"use client";
import { useState } from "react";
import { useOBDStream } from "@/hooks/useOBDStream";
import { useSettings, toDisplayTemp } from "@/lib/settings";
import { PIDCard } from "@/components/dashboard/PIDCard";
import { LiveChart } from "@/components/dashboard/LiveChart";
import { AnomalyBanner } from "@/components/dashboard/AnomalyBanner";
import { LoggerControl } from "@/components/dashboard/LoggerControl";
import { Modal } from "@/components/ui/modal";
import { Separator } from "@/components/ui/separator";

export default function DashboardPage() {
  const { connected, status, latest: r, history, anomalyReason } = useOBDStream();
  const { tempUnit } = useSettings();

  const [chartOpen, setChartOpen] = useState(false);
  const tempLabel = `°${tempUnit}`;
  const coolantNormal: [number, number] = tempUnit === "F" ? [158, 230] : [70, 110];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-100">Live Dashboard</h1>
        <LoggerControl status={status} wsConnected={connected} />
      </div>

      {r?.anomaly_flag ? <AnomalyBanner reason={anomalyReason} /> : null}

      {/* Primary diagnostics */}
      <div className="grid grid-cols-2 gap-3">
        <PIDCard label="MAF"  value={r?.maf_gs}   unit="g/s" decimals={2} normalRange={[1.5, 6.0]} />
        <PIDCard label="LTFT" value={r?.ltft_pct}  unit="%"   decimals={1} normalRange={[-10, 10]} />
        <PIDCard label="STFT" value={r?.stft_pct}  unit="%"   decimals={1} normalRange={[-10, 10]} />
        <PIDCard label="RPM"  value={r?.rpm}        unit="rpm" decimals={0} />
      </div>

      <Separator className="bg-slate-800" />

      <div>
        <div className="flex items-center justify-between mb-1">
          <p className="text-xs text-slate-500 uppercase tracking-wide">MAF &amp; Fuel Trim (last 120 samples)</p>
          <button
            onClick={() => setChartOpen(true)}
            className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
          >
            expand ↗
          </button>
        </div>
        <div
          className="cursor-pointer"
          onClick={() => setChartOpen(true)}
          title="Tap to expand"
        >
          <LiveChart data={history} />
        </div>
      </div>

      <Modal
        open={chartOpen}
        onClose={() => setChartOpen(false)}
        title="MAF & Fuel Trim"
        className="max-w-2xl"
      >
        <div className="px-2 pb-4">
          <LiveChart data={history} height="h-[55vh]" />
        </div>
      </Modal>

      <Separator className="bg-slate-800" />

      {/* Secondary PIDs */}
      <div className="grid grid-cols-2 gap-3">
        <PIDCard label="Coolant"  value={toDisplayTemp(r?.coolant_c, tempUnit)} unit={tempLabel} decimals={0} normalRange={coolantNormal} />
        <PIDCard label="IAT"      value={toDisplayTemp(r?.iat_c, tempUnit)}      unit={tempLabel} decimals={0} />
        <PIDCard label="MAP"      value={r?.map_kpa}      unit="kPa" decimals={0} />
        <PIDCard label="Throttle" value={r?.throttle_pct} unit="%"   decimals={1} />
        <PIDCard label="Speed"    value={r?.speed_kph}    unit="km/h" decimals={0} />
        <PIDCard label="Timing"   value={r?.timing_deg}   unit="°"   decimals={1} />
        <PIDCard label="O2 B1S1"  value={r?.o2_b1s1_v}   unit="V"   decimals={3} />
        <PIDCard label="O2 B1S2"  value={r?.o2_b1s2_v}   unit="V"   decimals={3} />
      </div>

      {status && (
        <p className="text-xs text-slate-600 text-center mt-1">
          {status.logging
            ? `Logging · ${status.elapsed_s.toFixed(0)}s elapsed`
            : "Not logging — press Start to begin"}
        </p>
      )}
    </div>
  );
}
