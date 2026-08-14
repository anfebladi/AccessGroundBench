import type { ReactNode } from "react";
import type { Dataset, Model, Provider } from "../../lib/api";
import type { PreflightSummary } from "../../lib/types";
import type { Tab } from "../../app/navigation";
import { Sidebar } from "./Sidebar";
import { useEffect, useState } from "react";
import { Button } from "../ui/button";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "../ui/sheet";
import { DatasetHeaderProvider } from "../../features/shared/DatasetHeaderContext";

export function AppShell({
  route,
  datasets,
  datasetsError,
  dataset,
  models,
  providers,
  evaluate,
  compareCount,
  resultsCount,
  onDatasetChange,
  children,
  dataLoading = false,
}: {
  route: Tab;
  datasets: Dataset[];
  datasetsError?: string | null;
  dataset: string;
  models: Model[];
  providers: Provider[];
  evaluate: PreflightSummary;
  compareCount: number;
  resultsCount: number;
  onDatasetChange: (value: string) => void;
  children: ReactNode;
  dataLoading?: boolean;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  useEffect(() => {
    try { setCollapsed(window.localStorage.getItem("agb.sidebar.collapsed") === "1"); } catch { /* storage unavailable */ }
  }, []);
  const toggleCollapsed = () => setCollapsed((value) => {
    const next = !value;
    try { window.localStorage.setItem("agb.sidebar.collapsed", next ? "1" : "0"); } catch { /* storage unavailable */ }
    return next;
  });
  return (
    <>
      <div
        className={`app-body grid items-start transition-[grid-template-columns] duration-[var(--dur-mid)] ease-[var(--ease)] max-[1023px]:grid-cols-1 ${collapsed ? "grid-cols-[64px_minmax(0,1fr)]" : "grid-cols-[var(--rail-width)_minmax(0,1fr)]"}`}
      >
        <div className="hidden p-2 max-[1023px]:block max-[1023px]:px-[var(--page-gutter)]">
          <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
            <SheetTrigger asChild>
              <Button type="button" variant="secondary" size="sm" aria-label="Open workflow menu">Menu</Button>
            </SheetTrigger>
            <SheetContent>
              <SheetTitle>Workflow</SheetTitle>
              <Sidebar
                id="mobile-rail"
                onNavigate={() => setMenuOpen(false)}
                route={route}
                datasets={datasets}
                dataset={dataset}
                models={models}
                providers={providers}
                evaluate={evaluate}
                compareCount={compareCount}
                resultsCount={resultsCount}
                loading={dataLoading}
              />
            </SheetContent>
          </Sheet>
        </div>
        <Sidebar
          route={route}
          datasets={datasets}
          dataset={dataset}
          models={models}
          providers={providers}
          evaluate={evaluate}
          compareCount={compareCount}
          resultsCount={resultsCount}
          collapsed={collapsed}
          loading={dataLoading}
          onToggleCollapsed={toggleCollapsed}
        />
        <main className="workspace-main min-w-0 max-w-[var(--content-max)] px-[var(--page-gutter)] pb-[var(--space-8)] pt-[var(--space-7)] min-[1280px]:px-[var(--space-6)] max-[767px]:px-[var(--space-4)] max-[767px]:pt-[var(--space-4)]">
          <DatasetHeaderProvider
            value={{ datasets, dataset, datasetsError, onDatasetChange, loading: dataLoading }}
          >
            {children}
          </DatasetHeaderProvider>
        </main>
      </div>
    </>
  );
}
