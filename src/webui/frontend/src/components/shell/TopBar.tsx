import type { Dataset } from "../../lib/api";
import { Icon } from "./icons";
import styles from "./Shell.module.css";

export function TopBar({
  datasets,
  dataset,
  onDatasetChange,
  onPalette,
}: {
  datasets: Dataset[];
  dataset: string;
  onDatasetChange: (v: string) => void;
  onPalette: () => void;
}) {
  const selected = datasets.find((x) => x.name === dataset);

  return (
    <header className={`app-header ${styles.appHeader}`}>
      <div className="brand">
        <span className="brand-mark" aria-hidden="true">
          AGB
        </span>
        <span className="brand-name">AccessGroundBench</span>
      </div>
      <div className="header-controls">
        <label htmlFor="dataset-select">DATASET</label>
        <select
          id="dataset-select"
          value={dataset}
          onChange={(e) => onDatasetChange(e.target.value)}
        >
          {!datasets.length && <option value="">Select dataset</option>}
          {datasets.map((x) => (
            <option key={x.name} value={x.name}>
              {x.is_archived ? `${x.name} (archived)` : x.name}
            </option>
          ))}
        </select>
        <span id="dataset-meta" className="meta">
          {selected
            ? `${selected.screen_count} screens, ${selected.image_count} images${selected.is_archived ? " -- archived, read-only" : ""}`
            : ""}
        </span>
        <button
          type="button"
          className="secondary small icon-btn"
          id="palette-trigger"
          data-icon="command"
          title="Command palette (Ctrl/Cmd+K)"
          aria-label="Open command palette"
          onClick={onPalette}
        >
          <Icon name="command" />
        </button>
      </div>
    </header>
  );
}
