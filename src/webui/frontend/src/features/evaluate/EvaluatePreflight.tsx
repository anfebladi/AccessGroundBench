import type { Preflight } from "../../lib/api";
import { Badge } from "../../components/ui/badge";
import { Alert, AlertDescription, AlertIcon, AlertTitle } from "../../components/ui/alert";

export function EvaluatePreflight({ preflight }: { preflight: Preflight | null }) {
  if (!preflight) return null;
  const remaining = preflight.expected_total - preflight.already_done;
  return <>
    <div className="mt-4 flex flex-wrap items-center gap-3">
      <Badge className={preflight.already_done ? "text-[var(--primary)]" : "text-[var(--muted)]"}>
        {preflight.already_done
          ? `Resuming -- ${remaining} of ${preflight.expected_total} queries left`
          : `${preflight.expected_total} queries planned`}
      </Badge>
      <span className="text-sm text-[var(--muted)]">
        Writes to <code>{preflight.results_csv}</code>
      </span>
    </div>
    {preflight.lock_present && (
      <Alert variant="warning">
        <AlertTitle>
          <AlertIcon variant="warning" />
          Results file is locked
        </AlertTitle>
        <AlertDescription>
          {preflight.lock_holder && (
            <>Held by <code>{preflight.lock_holder}</code>. </>
          )}
          If no run is actually active -- a crashed process leaves its lock
          behind -- enable <b>Override stale lock</b> under Advanced options, or
          this run will exit without doing anything.
        </AlertDescription>
      </Alert>
    )}
  </>;
}
