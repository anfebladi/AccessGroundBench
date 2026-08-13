import type { Manifest } from "./types";
import { Card } from "../../components/ui/card";
import { Badge } from "../../components/ui/badge";

export function CaptureHealth({
  manifest,
  available,
}: {
  manifest: Manifest | null;
  available: boolean;
}) {
  if (!available) {
    return (
      <div className="rounded-md border border-[var(--warn)]/40 bg-[var(--warn)]/10 p-3 text-sm">
        <span className="font-semibold">Warning</span>
        No <code>collection_manifest.json</code> for this dataset, so capture
        completeness and content drift are unknown.
      </div>
    );
  }
  if (!manifest) return null;
  const complete = manifest.expected_captures === manifest.successful_captures;
  const problems = manifest.problems || [];
  return (
    <Card className="mt-4 p-4">
      <div className="flex items-center justify-between gap-3 pb-3">
        <div>
          <h3>Capture health</h3>
          <p className="text-sm text-[var(--muted)]">
            Read this before trusting any number reported against this dataset.
          </p>
        </div>
        <div>
          <Badge className={complete ? "text-[var(--ok)]" : "text-[var(--err)]"}>
            {manifest.successful_captures}/{manifest.expected_captures} captures{" "}
            {complete ? "complete" : "-- incomplete"}
          </Badge>
        </div>
      </div>
      {problems.length ? (
        <div className="rounded-md border border-[var(--warn)]/40 bg-[var(--warn)]/10 p-3 text-sm">
          <span className="font-semibold">Warning</span>
          <b>
            {problems.length} warning{problems.length === 1 ? "" : "s"}
          </b>{" "}
          -- affected screens carry a caveat, they are not automatically
          excluded.
          <details className="mt-2">
            <summary>Show warning details</summary>
            <ul>
              {problems.map((problem, index) => (
                <li key={`${index}-${problem}`}>{problem}</li>
              ))}
            </ul>
          </details>
        </div>
      ) : (
        <p className="text-sm text-[var(--muted)]">
          No drift or contamination warnings recorded.
        </p>
      )}
    </Card>
  );
}
