const TALLY: Array<[string, string, string]> = [
  ["HIT", "Hit", "is-ok"],
  ["MISS", "Miss", ""],
  ["OFF-SCREEN", "Off-screen", ""],
  ["OFF-FRAME", "Off-frame", ""],
  ["LABEL-CHANGED", "Label changed", ""],
  ["API-ERROR", "API error", "is-err"],
];

export function RunTally({ counts }: { counts: Record<string, number> }) {
  return (
    <div id="run-tally" className="tally mt-3 flex flex-wrap gap-2">
      {TALLY.filter(([key]) => counts[key]).map(([key, label, cls]) => (
        <span className={`tally-item inline-flex items-baseline gap-1.5 rounded-[var(--radius-sm)] border border-[var(--border)] bg-[var(--surface-2)] px-2 py-1 text-xs ${cls === "is-ok" ? "border-transparent bg-[color-mix(in_srgb,var(--ok)_11%,transparent)] text-[var(--ok)]" : cls === "is-err" ? "border-transparent bg-[color-mix(in_srgb,var(--err)_12%,transparent)] text-[var(--err)]" : ""}`} key={key}>
          <b>{counts[key]}</b> {label}
        </span>
      ))}
    </div>
  );
}
