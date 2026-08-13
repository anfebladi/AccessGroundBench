import type { Dataset, Model, Provider } from "../../lib/api";
import type { PreflightSummary } from "../../lib/types";
import { ROUTE_GROUPS, routeLabel, type Tab } from "../../app/navigation";
import { Icon } from "./icons";
import styles from "./Shell.module.css";
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
    <nav id={id} className={`${styles.rail} ${collapsed ? styles.railCollapsed : ""}`} aria-label="Workflow">
      {id === "rail" && onToggleCollapsed && (
        <button type="button" className={styles.collapseToggle} onClick={onToggleCollapsed} aria-label={collapsed ? "Expand workflow sidebar" : "Collapse workflow sidebar"} title={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
          <Icon name="menu" size={20} />
        </button>
      )}
      {ROUTE_GROUPS.map(({ label, tabs }) => (
        <div key={label}>
          <p
            className="rail-group"
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
            >
              <span className="rail-icon" aria-hidden="true" data-icon={tab}>
                <Icon name={tab} />
              </span>
              <span className="rail-label">{routeLabel(tab)}</span>
              <span
                className={`rail-chip${
                  tab === "evaluate"
                    ? evaluate.tone === "error"
                      ? " is-err"
                      : evaluate.tone === "info"
                        ? " is-info"
                        : ""
                    : !chips[tab] &&
                        ["models", "compare", "results", "analyze"].includes(
                          tab,
                        )
                      ? " is-warn"
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
