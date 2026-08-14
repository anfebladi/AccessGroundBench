import type { ReactNode } from "react";
import type { Dataset, Model, Provider } from "../../lib/api";
import type { PreflightSummary } from "../../lib/types";
import type { Tab } from "../../app/navigation";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
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
  const nextStep = {
    dataset: { eyebrow: "Start here", text: dataset ? "Review your capture set before running a workflow." : "Choose a dataset to begin." },
    models: { eyebrow: "Set up", text: models.length ? "Your model roster is ready for an evaluation." : "Configure a model before evaluating." },
    evaluate: { eyebrow: "Run", text: evaluate.text || "Select a model and run an evaluation." },
    collect: { eyebrow: "Run", text: "Capture a fresh dataset when you need new evidence." },
    compare: { eyebrow: "Compare", text: compareCount ? "Compare selected model runs side by side." : "Collect results before comparing models." },
    results: { eyebrow: "Read", text: resultsCount ? "Inspect accuracy and evidence from your latest runs." : "Run an evaluation to populate results." },
    analyze: { eyebrow: "Read", text: resultsCount ? "Turn result files into statistical evidence." : "Results are needed before analysis can run." },
  }[route];
  return (
    <>
      <TopBar
        datasets={datasets}
        dataset={dataset}
        onDatasetChange={onDatasetChange}
        onPalette={onPalette}
        loading={dataLoading}
      />
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
        <main className="workspace-main min-w-0 max-w-[var(--content-max)] px-[var(--page-gutter)] pb-[var(--space-8)] pt-[var(--space-6)] min-[1280px]:px-[var(--space-6)] max-[767px]:px-[var(--space-4)] max-[767px]:pt-[var(--space-4)]">
          <div className="next-step" id="workflow-next-step" role="status" aria-live="polite">
            <span className="next-step-mark" aria-hidden="true" />
            <span className="next-step-copy"><span className="next-step-eyebrow">{nextStep.eyebrow}</span>{nextStep.text}</span>
          </div>
          {children}
        </main>
      </div>
    </>
  );
}
