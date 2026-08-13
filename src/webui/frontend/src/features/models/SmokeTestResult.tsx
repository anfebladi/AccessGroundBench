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
      <p className="state-loading">Querying {smoke.model.id} on {screen}...</p>
      <div className="row"><Skeleton className="skeleton-block grow" /><Skeleton className="skeleton-block" style={{width: 220}} /></div>
    </div>;
  if (smoke.result?.ok) return success;
  return (
    <Alert className="state-error">
      {smoke.result?.error || "The model call failed."}
    </Alert>
  );
}
