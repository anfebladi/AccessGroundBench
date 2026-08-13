import type { Model, SmokeResult } from "../../lib/api";
import type React from "react";
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
    return (
      <p className="state-loading">
        Querying {smoke.model.id} on {screen}...
      </p>
    );
  if (smoke.result?.ok) return success;
  return (
    <p className="state-error" role="alert">
      {smoke.result?.error || "The model call failed."}
    </p>
  );
}
