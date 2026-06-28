"use client";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { SessionList } from "@/components/sessions/SessionList";
import { SessionDetail } from "@/components/sessions/SessionDetail";

function SessionsContent() {
  const params = useSearchParams();
  const id = params.get("id");

  if (id) {
    return <SessionDetail sessionId={Number(id)} />;
  }
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold text-slate-100">Sessions</h1>
      <SessionList />
    </div>
  );
}

export default function SessionsPage() {
  return (
    <Suspense fallback={<p className="text-slate-500 text-sm">Loading…</p>}>
      <SessionsContent />
    </Suspense>
  );
}
