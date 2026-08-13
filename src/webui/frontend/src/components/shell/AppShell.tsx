import type { ReactNode } from "react";
import type { Dataset, Model, Provider } from "../../lib/api";
import type { PreflightSummary } from "../../lib/types";
import type { Tab } from "../../app/navigation";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import styles from "./Shell.module.css";
import { useEffect, useState } from "react";
import { Button } from "../ui/button";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "../ui/sheet";

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
  dataLoading = false,
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
      <TopBar
        datasets={datasets}
        dataset={dataset}
        onDatasetChange={onDatasetChange}
        onPalette={onPalette}
        loading={dataLoading}
      />
      <div className={`app-body ${styles.appBody} ${collapsed ? styles.bodyCollapsed : ""}`}>
        <div className={styles.mobileMenu}>
          <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
            <SheetTrigger asChild>
              <Button type="button" className="secondary small" aria-label="Open workflow menu">Menu</Button>
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
        <main>{children}</main>
      </div>
    </>
  );
}
