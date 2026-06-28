"use client";
import dynamic from "next/dynamic";
import type { Reading } from "@/lib/api";

const Chart = dynamic(() => import("./_ChartInner"), { ssr: false });

interface LiveChartProps {
  data: Reading[];
  height?: string;
}

export function LiveChart({ data, height }: LiveChartProps) {
  return <Chart data={data} height={height} />;
}
