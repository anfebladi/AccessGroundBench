import type { Manifest } from "./types";

export function CaptureHealth({
  manifest,
  available,
}: {
  manifest: Manifest | null;
  available: boolean;
}) {
  if (!available)
    return (
      <div className="note note-warn">
        <span className="note-label">Warning</span>No <code>collection_manifest.json</code> for this dataset, so capture completeness and content drift are unknown.
      </div>
    );
  if (!manifest) return null;
  const complete = manifest.expected_captures === manifest.successful_captures;
  const problems = manifest.problems || [];
  return (
    <div className="card">
      <div className="card-head">
        <div>
          <h3>Capture health</h3>
          <p className="card-sub">Read this before trusting any number reported against this dataset.</p>
        </div>
        <div className="card-head-actions">
          <span className={`badge ${complete ? "ok" : "err"}`}>
            {manifest.successful_captures}/{manifest.expected_captures} captures {complete ? "complete" : "-- incomplete"}
          </span>
        </div>
      </div>
      {problems.length ? (
        <div className="note note-warn">
          <span className="note-label">Warning</span>
          <b>{problems.length} warning{problems.length === 1 ? "" : "s"}</b> -- affected screens carry a caveat, they are not automatically excluded.
          <details className="advanced">
            <summary>Show warning details</summary>
            <ul>
              {problems.map((p, i) => <li key={`${i}-${p}`}>{p}</li>)}
            </ul>
          </details>
        </div>
      ) : <p className="muted small">No drift or contamination warnings recorded.</p>}
    </div>
  );
}
