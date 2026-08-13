import type { Dataset } from "../../lib/api";
import { Icon } from "./icons";
import { Button } from "../ui/button";
import { NativeSelect } from "../ui/native-select";
import { Skeleton } from "../ui/skeleton";

export function TopBar({
  datasets,
  dataset,
  onDatasetChange,
  onPalette,
  loading = false,
}: {
  datasets: Dataset[];
  dataset: string;
  onDatasetChange: (v: string) => void;
  onPalette: () => void;
  loading?: boolean;
}) {
  const selected = datasets.find((x) => x.name === dataset);

  return (
    <header className="app-header sticky top-0 z-30 flex min-h-[var(--header-height)] items-center justify-between gap-[var(--space-5)] border-b border-[var(--border)] bg-[var(--surface)] px-[var(--page-gutter)] py-2 text-[var(--text)] shadow-[var(--elev-card)] min-[1280px]:px-[var(--space-6)] max-[767px]:px-[var(--space-4)]">
      <div className="brand flex min-w-0 items-center gap-[var(--space-3)]">
        <span className="grid size-[26px] shrink-0 place-items-center rounded-[var(--radius-sm)] bg-[var(--primary)] font-mono text-[0.625rem] font-semibold tracking-[0.02em] text-[var(--primary-fg)]" aria-hidden="true">
          AGB
        </span>
        <span className="whitespace-nowrap font-display text-[0.9375rem] font-semibold tracking-[-0.01em] max-[479px]:text-sm">AccessGroundBench</span>
      </div>
      <div className="header-controls flex min-w-0 items-center gap-[var(--space-3)]">
        <label className="text-xs text-[var(--muted)]" htmlFor="dataset-select">DATASET</label>
        <NativeSelect
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
        </NativeSelect>
          <span id="dataset-meta" className="whitespace-nowrap text-sm text-[var(--muted)] max-[479px]:hidden">
          {loading ? <Skeleton className="h-4 w-32" aria-label="Loading dataset" /> : selected
            ? `${selected.screen_count} screens, ${selected.image_count} images${selected.is_archived ? " -- archived, read-only" : ""}`
            : ""}
        </span>
        <Button
          type="button"
          variant="secondary"
          size="icon"
          className="shrink-0"
          id="palette-trigger"
          data-icon="command"
          title="Command palette (Ctrl/Cmd+K)"
          aria-label="Open command palette"
          onClick={onPalette}
        >
          <Icon name="command" />
        </Button>
      </div>
    </header>
  );
}
