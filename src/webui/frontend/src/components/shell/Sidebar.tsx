import type { Dataset, Model, Provider } from "../../lib/api";
import type { PreflightSummary } from "../../lib/types";
import { ROUTE_GROUPS, routeLabel, type Tab } from "../../app/navigation";
import { Icon } from "./icons";
import { Spinner } from "../ui/spinner";

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
    dataset: selected ? `${selected.screen_count} screens` : "",
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
      className={`${id === "rail" ? "max-[1023px]:hidden" : ""} sticky top-[var(--space-3)] m-3 min-h-[calc(100vh-var(--space-6))] max-h-[calc(100vh-var(--space-6))] overflow-y-auto rounded-[var(--radius-lg)] bg-[var(--surface-warm)] p-[var(--space-4)_var(--space-3)] shadow-[var(--elev-card)] max-[1023px]:top-0 max-[1023px]:z-20 max-[1023px]:m-0 max-[1023px]:flex max-[1023px]:min-h-0 max-[1023px]:max-h-none max-[1023px]:gap-1 max-[1023px]:overflow-x-auto max-[1023px]:overflow-y-hidden max-[1023px]:rounded-none max-[1023px]:border-b max-[1023px]:border-[var(--border)] max-[1023px]:px-[var(--page-gutter)] max-[1023px]:pb-0 max-[1023px]:pt-2 max-[1023px]:shadow-none max-[1023px]:[scrollbar-width:thin] ${collapsed ? "w-16 [&_.rail-group]:m-0 [&_.rail-group]:text-center [&_.rail-group]:text-[0px] [&_.rail-group-label]:hidden [&_a]:grid-cols-1 [&_a]:grid-rows-1 [&_a]:justify-items-center [&_a]:px-2 [&_.rail-label]:hidden [&_.rail-chip]:hidden [&_.rail-icon]:[grid-row:auto] [&_.rail-brand]:hidden" : ""}`}
      aria-label="Workflow"
    >
      {id === "rail" && onToggleCollapsed && (
        <div className="mb-3 flex items-center gap-2 max-[1023px]:hidden">
          <button
            type="button"
            className="grid size-10 min-h-10 min-w-10 shrink-0 cursor-pointer place-items-center rounded-[var(--radius-md)] border-0 bg-transparent p-0 text-[var(--muted)] transition-colors hover:bg-[var(--gray-100)] hover:text-[var(--text)] focus-visible:outline-2 focus-visible:outline-[var(--primary)] focus-visible:outline-offset-2"
            onClick={onToggleCollapsed}
            aria-label={
              collapsed ? "Expand workflow sidebar" : "Collapse sidebar"
            }
          >
            <Icon name="menu" size={20} />
          </button>
          <span className="rail-brand whitespace-nowrap font-display text-[0.9375rem] font-semibold tracking-[-0.025em] text-[var(--text)]">
            AccessGroundBench
          </span>
        </div>
      )}
      {ROUTE_GROUPS.map(({ label, tabs }) => (
        <div key={label}>
          <p
            className="rail-group mb-2 mt-7 px-2 text-xs font-semibold uppercase tracking-[0.04em] text-black max-[1023px]:hidden"
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
              key={tab}
              onClick={onNavigate}
              className="mb-1 grid min-h-[36px] grid-cols-[24px_minmax(0,1fr)] items-center gap-x-2 rounded-[var(--radius-full)] p-2 text-[var(--text-2)] no-underline transition-[background-color,color,box-shadow] duration-[var(--dur-fast)] ease-[var(--ease)] hover:bg-[var(--surface-2)] hover:text-[var(--text)] aria-[current=page]:bg-[var(--surface)] aria-[current=page]:text-[var(--primary)] aria-[current=page]:shadow-[var(--elev-neumorph)] max-[1023px]:flex max-[1023px]:min-h-[34px] max-[1023px]:shrink-0 max-[1023px]:gap-2 max-[1023px]:rounded-full max-[1023px]:border-b-2 max-[1023px]:border-transparent max-[1023px]:pb-2 max-[1023px]:hover:border-transparent max-[1023px]:aria-[current=page]:border-[var(--primary)] max-[1023px]:aria-[current=page]:shadow-none"
            >
              <span
                className="rail-icon grid size-6 place-items-center text-[var(--muted)]"
                aria-hidden="true"
                data-icon={tab}
              >
                <Icon name={tab} />
              </span>
              <span className="flex min-w-0 flex-col justify-center">
                <span className="rail-label text-sm font-medium">
                  {routeLabel(tab)}
                </span>
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
                  {loading &&
                  ["dataset", "models", "compare", "results"].includes(tab) ? (
                    <Spinner label="Loading" className="size-3 border" />
                  ) : (
                    chips[tab] || null
                  )}
                </span>
              </span>
            </a>
          ))}
        </div>
      ))}
    </nav>
  );
}
