import type { Dataset, Model, Provider } from "../../lib/api";
import type { PreflightSummary } from "../../lib/types";
import { ROUTE_GROUPS, routeLabel, type Tab } from "../../app/navigation";
import { Icon } from "./icons";
import { Skeleton } from "../ui/skeleton";

export function Sidebar({
  route,
  datasets,
  dataset,
  models,
  providers,
  evaluate,
  compareCount,
  resultsCount,
  onNavigate,
  id = "rail",
  collapsed = false,
  loading = false,
  onToggleCollapsed,
}: {
  route: Tab;
  datasets: Dataset[];
  dataset: string;
  models: Model[];
  providers: Provider[];
  evaluate: PreflightSummary;
  compareCount: number;
  resultsCount: number;
  onNavigate?: () => void;
  id?: string;
  collapsed?: boolean;
  loading?: boolean;
  onToggleCollapsed?: () => void;
}) {
  const selected = datasets.find((x) => x.name === dataset);
  const configured = providers.filter(
    (p) => p.configured || p.env_configured || p.session_configured,
  ).length;
  const chips: Record<Tab, string> = {
    dataset: selected
      ? selected.is_archived
        ? "archived, read-only"
        : `${selected.screen_count} screens`
      : "",
    models: models.length
      ? `${models.length} model${models.length === 1 ? "" : "s"}, ${configured} provider${configured === 1 ? "" : "s"}`
      : "none configured",
    evaluate: evaluate.text,
    collect: "",
    compare: compareCount
      ? `${compareCount} model${compareCount === 1 ? "" : "s"}`
      : "needs results",
    results: resultsCount
      ? `${resultsCount} result file${resultsCount === 1 ? "" : "s"}`
      : "no runs yet",
    analyze: resultsCount ? "" : "needs results",
  };

  return (
    <nav
      id={id}
      className={`${id === "rail" ? "max-[1023px]:hidden" : ""} sticky top-[var(--header-height)] max-h-[calc(100vh-var(--header-height))] overflow-y-auto border-r border-[var(--border)] bg-[var(--surface-warm)]/70 p-[var(--space-4)_var(--space-3)] max-[1023px]:z-20 max-[1023px]:flex max-[1023px]:max-h-none max-[1023px]:gap-1 max-[1023px]:overflow-x-auto max-[1023px]:overflow-y-hidden max-[1023px]:border-r-0 max-[1023px]:border-b max-[1023px]:px-[var(--page-gutter)] max-[1023px]:pb-0 max-[1023px]:pt-2 max-[1023px]:[scrollbar-width:thin] ${collapsed ? "w-16 [&_.rail-group]:m-0 [&_.rail-group]:text-center [&_.rail-group]:text-[0px] [&_.rail-group-label]:hidden [&_a]:grid-cols-1 [&_a]:grid-rows-1 [&_a]:justify-items-center [&_a]:px-2 [&_.rail-label]:hidden [&_.rail-chip]:hidden [&_.rail-icon]:[grid-row:auto]" : ""}`}
      aria-label="Workflow"
    >
      {id === "rail" && onToggleCollapsed && (
        <button type="button" className="mb-3 grid size-10 min-h-10 min-w-10 place-items-center rounded-md border-0 bg-transparent p-0 text-[var(--muted)] transition-colors hover:bg-[var(--gray-100)] hover:text-[var(--text)] focus-visible:outline-2 focus-visible:outline-[var(--primary)] focus-visible:outline-offset-2 max-[1023px]:hidden" onClick={onToggleCollapsed} aria-label={collapsed ? "Expand workflow sidebar" : "Collapse sidebar"} title={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
          <Icon name="menu" size={20} />
        </button>
      )}
      {ROUTE_GROUPS.map(({ label, tabs }) => (
        <div key={label}>
          <p
            className="rail-group mb-2 mt-4 px-2 text-xs font-semibold uppercase tracking-[0.04em] text-[var(--muted)] first:mt-0 max-[1023px]:hidden"
            id={label === "Set up" ? "rail-group-setup" : undefined}
          >
            <span className="rail-group-label">{label}</span>
          </p>
          {tabs.map((tab) => (
            <a
              href={`#${tab}`}
              data-tab={tab}
              aria-current={route === tab ? "page" : undefined}
              aria-label={routeLabel(tab)}
              title={collapsed ? routeLabel(tab) : undefined}
              key={tab}
              onClick={onNavigate}
              className="mb-px grid min-h-[34px] grid-cols-[20px_minmax(0,1fr)] grid-rows-[auto_auto] items-center gap-x-2 rounded-md p-2 text-[var(--text-2)] no-underline transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--text)] aria-[current=page]:bg-[var(--primary-soft)] aria-[current=page]:text-[var(--primary)] max-[1023px]:flex max-[1023px]:min-h-[34px] max-[1023px]:shrink-0 max-[1023px]:gap-2 max-[1023px]:rounded-b-none max-[1023px]:border-b-2 max-[1023px]:border-transparent max-[1023px]:pb-2 max-[1023px]:hover:border-transparent max-[1023px]:aria-[current=page]:border-[var(--primary)]"
            >
              <span className="rail-icon row-span-2 grid size-5 place-items-center text-[var(--muted)] max-[1023px]:row-span-1" aria-hidden="true" data-icon={tab}>
                <Icon name={tab} />
              </span>
              <span className="rail-label text-sm font-medium">{routeLabel(tab)}</span>
              <span
                className={`rail-chip overflow-hidden text-ellipsis whitespace-nowrap text-xs text-[var(--muted)] empty:hidden max-[1023px]:hidden ${
                  tab === "evaluate"
                    ? evaluate.tone === "error"
                      ? " text-[var(--warn)]"
                      : evaluate.tone === "info"
                        ? " text-[var(--primary)]"
                        : ""
                    : !chips[tab] &&
                        ["models", "compare", "results", "analyze"].includes(
                          tab,
                        )
                      ? " text-[var(--warn)]"
                      : ""
                }`}
                data-chip={tab}
              >
                {loading && ["dataset", "models", "compare", "results"].includes(tab) ? <Skeleton className="rail-chip-skeleton" aria-label="Loading" /> : chips[tab]}
              </span>
            </a>
          ))}
        </div>
      ))}
    </nav>
  );
}
