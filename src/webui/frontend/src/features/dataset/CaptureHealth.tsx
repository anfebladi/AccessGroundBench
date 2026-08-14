import type { Manifest } from "./types";
import { Card } from "../../components/ui/card";
import { Alert, AlertDescription, AlertIcon, AlertTitle } from "../../components/ui/alert";
import {
  Collapsible,
  CollapsibleContent,
  DisclosureTrigger,
} from "../../components/ui/collapsible";

export function CaptureHealth({
  manifest,
  available,
}: {
  manifest: Manifest | null;
  available: boolean;
}) {
  if (!available) {
    return (
      <Alert variant="warning">
        <AlertTitle>
          <AlertIcon variant="warning" />
          Capture health unknown
        </AlertTitle>
        <AlertDescription>
          No <code>collection_manifest.json</code> for this dataset, so capture
          completeness and content drift are unknown.
        </AlertDescription>
      </Alert>
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
        <span className={complete ? "text-[var(--ok)]" : "text-[var(--err)]"}>
          {manifest.successful_captures}/{manifest.expected_captures} captures{" "}
          {complete ? "complete" : "-- incomplete"}
        </span>
      </div>
      {problems.length ? (
        <Alert variant="warning">
          <AlertTitle>
            <AlertIcon variant="warning" />
            {problems.length} warning{problems.length === 1 ? "" : "s"}
          </AlertTitle>
          <AlertDescription>
            Affected screens carry a caveat, they are not automatically
            excluded.
            <Collapsible className="mt-2">
              <DisclosureTrigger>Show warning details</DisclosureTrigger>
              <CollapsibleContent>
                <ul className="mt-1.5 space-y-1">
                  {problems.map((problem, index) => (
                    <li key={`${index}-${problem}`}>{problem}</li>
                  ))}
                </ul>
              </CollapsibleContent>
            </Collapsible>
          </AlertDescription>
        </Alert>
      ) : (
        <p className="text-sm text-[var(--muted)]">
          No drift or contamination warnings recorded.
        </p>
      )}
    </Card>
  );
}
