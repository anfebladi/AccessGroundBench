import type { Dataset, Model, Provider } from "../../lib/api";
import type { PreflightSummary } from "../../lib/types";
import { ROUTE_GROUPS, routeLabel, type Tab } from "../../app/navigation";
import { Icon } from "./icons";
import styles from "./Shell.module.css";

export function Sidebar({
  route,
  datasets,
  dataset,
  models,
  providers,
  evaluate,
  compareCount,
  resultsCount,
}: {
  route: Tab;
  datasets: Dataset[];
  dataset: string;
  models: Model[];
  providers: Provider[];
  evaluate: PreflightSummary;
  compareCount: number;
  resultsCount: number;
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
    <nav id="rail" className={styles.rail} aria-label="Workflow">
      {ROUTE_GROUPS.map(({ label, tabs }) => (
        <div key={label}>
          <p
            className="rail-group"
            id={label === "Set up" ? "rail-group-setup" : undefined}
          >
            {label}
          </p>
          {tabs.map((tab) => (
            <a
              href={`#${tab}`}
              data-tab={tab}
              aria-current={route === tab ? "page" : undefined}
              key={tab}
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
                {chips[tab]}
              </span>
            </a>
          ))}
        </div>
      ))}
    </nav>
  );
}
