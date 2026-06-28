"use client";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import type { Reading } from "@/lib/api";

interface Props { data: Reading[]; height?: string }

const COLORS = {
  maf:  "#38bdf8",
  stft: "#facc15",
  ltft: "#f97316",
  rpm:  "#a78bfa",
};

function fmt(n: number | null | undefined, d = 1): string {
  return n != null ? n.toFixed(d) : "—";
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-slate-900 border border-slate-700 rounded px-3 py-2 text-xs text-slate-200">
      <p className="text-slate-400 mb-1">{Number(label).toFixed(0)} s</p>
      {payload.map((p: any) => (
        <p key={p.name} style={{ color: p.color }}>
          {p.name}: {p.value != null ? Number(p.value).toFixed(2) : "—"}
        </p>
      ))}
    </div>
  );
};

export default function ChartInner({ data, height = "h-64" }: Props) {
  return (
    <div className={`w-full ${height} mt-2`}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 4, right: 8, left: -10, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis
            dataKey="elapsed_s"
            type="number"
            domain={["auto", "auto"]}
            tickFormatter={(v) => `${Math.round(v)}s`}
            tick={{ fill: "#64748b", fontSize: 10 }}
            stroke="#334155"
          />
          {/* Left axis: MAF g/s */}
          <YAxis
            yAxisId="maf"
            domain={[0, 10]}
            tick={{ fill: "#64748b", fontSize: 10 }}
            stroke="#334155"
            label={{ value: "g/s", angle: -90, position: "insideLeft", fill: "#64748b", fontSize: 9 }}
          />
          {/* Right axis: fuel trim % */}
          <YAxis
            yAxisId="ft"
            orientation="right"
            domain={[-30, 30]}
            tick={{ fill: "#64748b", fontSize: 10 }}
            stroke="#334155"
            label={{ value: "%", angle: 90, position: "insideRight", fill: "#64748b", fontSize: 9 }}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend
            wrapperStyle={{ fontSize: 10, color: "#94a3b8" }}
            formatter={(val) => <span style={{ color: "#94a3b8" }}>{val}</span>}
          />
          <ReferenceLine yAxisId="ft" y={10}  stroke="#22c55e" strokeDasharray="4 4" strokeOpacity={0.5} />
          <ReferenceLine yAxisId="ft" y={-10} stroke="#22c55e" strokeDasharray="4 4" strokeOpacity={0.5} />
          <Line
            yAxisId="maf"
            type="monotone"
            dataKey="maf_gs"
            name="MAF"
            stroke={COLORS.maf}
            dot={false}
            strokeWidth={2}
            isAnimationActive={false}
          />
          <Line
            yAxisId="ft"
            type="monotone"
            dataKey="stft_pct"
            name="STFT"
            stroke={COLORS.stft}
            dot={false}
            strokeWidth={1.5}
            isAnimationActive={false}
          />
          <Line
            yAxisId="ft"
            type="monotone"
            dataKey="ltft_pct"
            name="LTFT"
            stroke={COLORS.ltft}
            dot={false}
            strokeWidth={1.5}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
