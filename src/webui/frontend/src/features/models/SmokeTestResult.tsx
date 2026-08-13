import type { Model, SmokeResult } from "../../lib/api";
import type React from "react";
import { Alert } from "../../components/ui/alert";
import { Skeleton } from "../../components/ui/skeleton";
export function SmokeTestResult({
  smoke,
  dataset,
  screen,
  success,
}: {
  smoke: { model: Model; loading?: boolean; result?: SmokeResult };
  dataset?: string;
  screen?: string;
  success: React.ReactNode;
}) {
  if (smoke.loading)
    return <div aria-label={`Querying ${smoke.model.id} on ${screen}`}>
      <p className="text-sm text-[var(--muted)]">Querying {smoke.model.id} on {screen}...</p>
      <div className="flex items-center gap-3"><Skeleton className="h-24 min-w-0 flex-1" /><Skeleton className="h-24 w-[220px]" /></div>
    </div>;
  if (smoke.result?.ok) return success;
  return (
    <Alert className="rounded-md border border-[var(--err)]/40 bg-[var(--err)]/10 p-3 text-sm text-[var(--err)]">
      {smoke.result?.error || "The model call failed."}
    </Alert>
  );
}
