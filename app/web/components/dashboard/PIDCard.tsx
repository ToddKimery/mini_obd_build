"use client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface PIDCardProps {
  label: string;
  value: number | null | undefined;
  unit: string;
  decimals?: number;
  normalRange?: [number, number];
  className?: string;
}

export function PIDCard({
  label,
  value,
  unit,
  decimals = 1,
  normalRange,
  className,
}: PIDCardProps) {
  const display = value != null ? value.toFixed(decimals) : "—";

  const outOfRange =
    value != null && normalRange != null
      ? value < normalRange[0] || value > normalRange[1]
      : false;

  return (
    <Card
      className={cn(
        "bg-slate-800 border-slate-700 transition-colors",
        outOfRange && "border-red-500 bg-red-950/30",
        className
      )}
    >
      <CardHeader className="pb-1 pt-3 px-4">
        <CardTitle className="text-xs font-medium text-slate-400 uppercase tracking-wide">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-3">
        <div className="flex items-end gap-1.5">
          <span
            className={cn(
              "text-3xl font-bold tabular-nums",
              outOfRange ? "text-red-400" : "text-slate-100"
            )}
          >
            {display}
          </span>
          <span className="text-sm text-slate-500 mb-1">{unit}</span>
        </div>
        {normalRange != null && value != null && (
          <Badge
            variant="outline"
            className={cn(
              "mt-1 text-xs px-1.5 py-0",
              outOfRange
                ? "border-red-700 text-red-400"
                : "border-emerald-700 text-emerald-400"
            )}
          >
            {outOfRange ? "out of range" : "normal"}
          </Badge>
        )}
      </CardContent>
    </Card>
  );
}
