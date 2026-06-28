"use client";
import dynamic from "next/dynamic";
import type { Reading } from "@/lib/api";

// Recharts must be dynamically imported (no SSR) for static export
const Chart = dynamic(() => import("./_ChartInner"), { ssr: false });

interface LiveChartProps {
  data: Reading[];
}

export function LiveChart({ data }: LiveChartProps) {
  return <Chart data={data} />;
}
