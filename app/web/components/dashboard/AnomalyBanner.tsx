"use client";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { cn } from "@/lib/utils";

interface AnomalyBannerProps {
  reason: string;
  className?: string;
}

export function AnomalyBanner({ reason, className }: AnomalyBannerProps) {
  if (!reason) return null;
  return (
    <Alert
      className={cn(
        "border-red-600 bg-red-950/60 text-red-300",
        className
      )}
    >
      <AlertTitle className="text-red-400 font-semibold">Anomaly Detected</AlertTitle>
      <AlertDescription className="text-red-300 text-sm">{reason}</AlertDescription>
    </Alert>
  );
}
