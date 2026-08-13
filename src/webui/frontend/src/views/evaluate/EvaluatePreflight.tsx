import type { Preflight } from "../../lib/api";

export function EvaluatePreflight({ preflight }: { preflight: Preflight | null }) {
  if (!preflight) return null;
  const remaining = preflight.expected_total - preflight.already_done;
  return <>
    <div style={{ marginTop: "var(--space-4)", display: "flex", gap: "var(--space-3)", alignItems: "center", flexWrap: "wrap" }}>
      <span className={`badge ${preflight.already_done ? "info" : "muted"}`}>{preflight.already_done ? `Resuming -- ${remaining} of ${preflight.expected_total} queries left` : `${preflight.expected_total} queries planned`}</span>
      <span className="field-hint">Writes to <code>{preflight.results_csv}</code></span>
    </div>
    {preflight.lock_present && <div className="note note-warn"><span className="note-label">Warning</span>{" "}<b>This results file is locked.</b>{preflight.lock_holder && <> Held by <code>{preflight.lock_holder}</code>.</>} If no run is actually active -- a crashed process leaves its lock behind -- enable <b>Override stale lock</b> under Advanced options, or this run will exit without doing anything.</div>}
  </>;
}
