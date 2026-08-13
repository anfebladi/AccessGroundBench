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
    <div id="run-tally" className="tally">
      {TALLY.filter(([key]) => counts[key]).map(([key, label, cls]) => (
        <span className={`tally-item ${cls}`} key={key}>
          <b>{counts[key]}</b> {label}
        </span>
      ))}
    </div>
  );
}
