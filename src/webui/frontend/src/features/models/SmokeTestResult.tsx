import type { Model, SmokeResult } from "../../lib/api";
import type React from "react";
import { Alert } from "../../components/ui/alert";
import { Spinner } from "../../components/ui/spinner";
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
    return <div className="flex items-center gap-3 rounded-[var(--radius-md)] bg-[var(--surface-2)] p-3" role="status" aria-busy="true" aria-label={`Querying ${smoke.model.id} on ${screen}`}>
      <Spinner className="size-4" />
      <p className="text-sm text-[var(--muted)]">Querying {smoke.model.id} on {screen}...</p>
    </div>;
  if (smoke.result?.ok) return success;
  return (
    <Alert className="rounded-md border border-[var(--err)]/40 bg-[var(--err)]/10 p-3 text-sm text-[var(--err)]">
      {smoke.result?.error || "The model call failed."}
    </Alert>
  );
}
