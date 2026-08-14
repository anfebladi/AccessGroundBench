import type { ReactNode } from "react";
import { routeGroupLabel, type Tab } from "../../app/navigation";
import { useDatasetHeader } from "./DatasetHeaderContext";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/ui/select";
import { Spinner } from "../../components/ui/spinner";

/**
 * The opening block of every workflow stage: phase eyebrow, title, and lead
 * description. The eyebrow comes from the sidebar's route groups so the phase
 * label is authored once. The eyebrow row also carries the dataset picker
 * (via DatasetHeaderContext) so it lines up with "SET UP" on every view
 * without threading dataset props through each one.
 */
export function StageHeader({
  stage,
  title,
  children,
}: {
  stage: Tab;
  title: string;
  children: ReactNode;
}) {
  const datasetHeader = useDatasetHeader();
  const selected = datasetHeader?.datasets.find((x) => x.name === datasetHeader.dataset);

  return (
    <div className="view-head mb-[var(--space-5)]">
      <div className="mb-2 flex items-center justify-between gap-[var(--space-3)] pr-1">
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--primary)]">
          {routeGroupLabel(stage)}
        </p>
        {datasetHeader && (
          <div className="header-controls flex min-w-0 items-center gap-[var(--space-3)]">
            <label className="text-xs text-[var(--muted)]" htmlFor="dataset-select">DATASET</label>
            <Select value={datasetHeader.dataset} onValueChange={datasetHeader.onDatasetChange}>
              <SelectTrigger id="dataset-select" className="min-w-[160px] rounded-[var(--radius-full)] border-transparent bg-[var(--surface-2)] hover:border-transparent hover:bg-[var(--surface-3)]" title={datasetHeader.datasetsError ?? undefined}>
                <SelectValue placeholder={datasetHeader.datasetsError ? "Failed to load datasets" : "Select dataset"} />
              </SelectTrigger>
              <SelectContent>
                {datasetHeader.datasets.map((x) => (
                  <SelectItem key={x.name} value={x.name}>
                    {x.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <span id="dataset-meta" className="whitespace-nowrap text-sm text-[var(--muted)] max-[479px]:hidden">
              {datasetHeader.loading ? <Spinner label="Loading dataset" className="size-4 align-middle" /> : selected
                ? `${selected.screen_count} screens, ${selected.image_count} images, ${selected.query_count} queries`
                : ""}
            </span>
          </div>
        )}
      </div>
      <div className="max-w-[var(--prose-max)]">
        <h2
          id={`head-${stage}`}
          className="text-[length:var(--text-display)] leading-[var(--lh-display)] tracking-[var(--ls-display)] max-[767px]:text-[1.375rem]"
        >
          {title}
        </h2>
        <p className="mt-2 font-[var(--font-ui)] text-[length:var(--text-lead)] leading-[var(--lh-lead)] text-[var(--text-2)]">
          {children}
        </p>
      </div>
    </div>
  );
}
