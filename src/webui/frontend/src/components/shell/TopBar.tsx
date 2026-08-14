import type { Dataset } from "../../lib/api";
import { NativeSelect } from "../ui/native-select";
import { Spinner } from "../ui/spinner";

export function TopBar({
  datasets,
  datasetsError,
  dataset,
  onDatasetChange,
  loading = false,
}: {
  datasets: Dataset[];
  datasetsError?: string | null;
  dataset: string;
  onDatasetChange: (v: string) => void;
  loading?: boolean;
}) {
  const selected = datasets.find((x) => x.name === dataset);

  return (
    <header className="app-header sticky top-0 z-30 flex min-h-[var(--header-height)] items-center justify-between gap-[var(--space-5)] border-b border-[var(--border)] bg-[var(--surface)] px-[var(--page-gutter)] py-2 text-[var(--text)] shadow-[var(--elev-card)] min-[1280px]:px-[var(--space-6)] max-[767px]:px-[var(--space-4)]">
      <div className="brand flex min-w-0 items-center gap-[var(--space-3)]">
        <span className="whitespace-nowrap font-display text-[0.9375rem] font-semibold tracking-[-0.01em] max-[479px]:text-sm">AccessGroundBench</span>
      </div>
      <div className="header-controls flex min-w-0 items-center gap-[var(--space-3)]">
        <label className="text-xs text-[var(--muted)]" htmlFor="dataset-select">DATASET</label>
        <NativeSelect
          id="dataset-select"
          value={dataset}
          onChange={(e) => onDatasetChange(e.target.value)}
          title={datasetsError ?? undefined}
        >
          {!datasets.length && (
            <option value="">
              {datasetsError ? "Failed to load datasets" : "Select dataset"}
            </option>
          )}
          {datasets.map((x) => (
            <option key={x.name} value={x.name}>
              {x.name}
            </option>
          ))}
        </NativeSelect>
          <span id="dataset-meta" className="whitespace-nowrap text-sm text-[var(--muted)] max-[479px]:hidden">
          {loading ? <Spinner label="Loading dataset" className="size-4 align-middle" /> : selected
            ? `${selected.screen_count} screens, ${selected.image_count} images, ${selected.query_count} queries`
            : ""}
        </span>
      </div>
    </header>
  );
}
