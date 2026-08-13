import type { ReactNode } from "react";
import type { Dataset, Model, Provider } from "../../lib/api";
import type { PreflightSummary } from "../../lib/types";
import type { Tab } from "../../app/navigation";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import styles from "./Shell.module.css";

export function AppShell({
  route,
  datasets,
  dataset,
  models,
  providers,
  evaluate,
  compareCount,
  resultsCount,
  onDatasetChange,
  onPalette,
  children,
}: {
  route: Tab;
  datasets: Dataset[];
  dataset: string;
  models: Model[];
  providers: Provider[];
  evaluate: PreflightSummary;
  compareCount: number;
  resultsCount: number;
  onDatasetChange: (value: string) => void;
  onPalette: () => void;
  children: ReactNode;
}) {
  return (
    <>
      <TopBar
        datasets={datasets}
        dataset={dataset}
        onDatasetChange={onDatasetChange}
        onPalette={onPalette}
      />
      <div className={`app-body ${styles.appBody}`}>
        <Sidebar
          route={route}
          datasets={datasets}
          dataset={dataset}
          models={models}
          providers={providers}
          evaluate={evaluate}
          compareCount={compareCount}
          resultsCount={resultsCount}
        />
        <main>{children}</main>
      </div>
    </>
  );
}
