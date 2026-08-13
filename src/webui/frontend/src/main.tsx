import { useCallback, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
import { AnalyzeView, CompareView, ResultsView } from "./reporting/views";
import { api, isTerminalRunStatus, readModels, type Model } from "./lib/api";
import { CollectView } from "./views/CollectView";
import { DatasetView } from "./views/DatasetView";
import { EvaluateView, type PreflightSummary } from "./views/EvaluateView";
import { ModelsView } from "./views/ModelsView";
import {
  AppErrorBoundary,
  Header,
  Palette,
  Rail,
  RouteView,
} from "./app/shell";
import { useAppData, useHashRoute, useKeyboardPalette } from "./app/hooks";
import { normalizeTab, TABS, type PaletteItem, type Tab } from "./app/routes";

export { api, isTerminalRunStatus, normalizeTab, TABS };
export type { Tab };

export function App() {
  const [route, go] = useHashRoute();
  const data = useAppData();
  const [models, setModels] = useState<Model[]>(readModels);
  const [evaluateSummary, setEvaluateSummary] = useState<PreflightSummary>({
    text: "",
    tone: "muted",
  });
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [paletteScreen, setPaletteScreen] = useState<string>();
  useKeyboardPalette(go, setPaletteOpen);

  const items = useMemo<PaletteItem[]>(
    () => [
      ...TABS.map((tab) => ({
        label: tab[0].toUpperCase() + tab.slice(1),
        hint: "View" as const,
        tab,
      })),
      ...data.screens.map((screen) => ({
        label: screen,
        hint: "Screen" as const,
        tab: "dataset" as Tab,
        screen,
      })),
      ...models.map((model) => ({
        label: model.id,
        hint: "Model" as const,
        tab: "models" as Tab,
      })),
      ...(
        [
          ["Run an evaluation", "evaluate"],
          ["Run an analysis", "analyze"],
          ["Compare a model against baseline", "compare"],
          ["Collect a new dataset", "collect"],
        ] as const
      ).map(([label, tab]) => ({ label, hint: "Action" as const, tab })),
    ],
    [data.screens, models],
  );
  const selectPalette = (item: PaletteItem) => {
    if (item.screen) setPaletteScreen(item.screen);
    go(item.tab);
    setPaletteOpen(false);
  };
  const onEvaluateSummary = useCallback(
    (summary: PreflightSummary) =>
      setEvaluateSummary((current) =>
        current.text === summary.text && current.tone === summary.tone
          ? current
          : summary,
      ),
    [],
  );
  const onCompareCount = useCallback(
    (count: number) =>
      data.setCompareCount((current) => (current === count ? current : count)),
    [data.setCompareCount],
  );
  const onResultsCount = useCallback(
    (count: number) =>
      data.setResultCount((current) => (current === count ? current : count)),
    [data.setResultCount],
  );
  const onRunFinished = () => {
    void data.refresh();
    if (data.dataset) void data.refreshDatasetData(data.dataset);
  };

  return (
    <>
      <Header
        datasets={data.datasets}
        dataset={data.dataset}
        onDatasetChange={data.setDataset}
        onPalette={() => setPaletteOpen(true)}
      />
      <div className="app-body">
        <Rail
          route={route}
          datasets={data.datasets}
          dataset={data.dataset}
          models={models}
          providers={data.providers}
          evaluate={evaluateSummary}
          compareCount={data.compareCount}
          resultsCount={data.resultCount}
        />
        <main>
          <RouteView tab="dataset" active={route === "dataset"}>
            <DatasetView
              dataset={data.dataset}
              datasets={data.datasets}
              screenToSelect={paletteScreen}
            />
          </RouteView>
          <RouteView tab="models" active={route === "models"}>
            <ModelsView
              onChange={setModels}
              dataset={data.dataset}
              screen={data.screens[0]}
            />
          </RouteView>
          <RouteView tab="evaluate" active={route === "evaluate"}>
            <EvaluateView
              dataset={data.dataset}
              models={models}
              onPreflightSummary={onEvaluateSummary}
              onRunFinished={onRunFinished}
            />
          </RouteView>
          <RouteView tab="collect" active={route === "collect"}>
            <CollectView onRunFinished={onRunFinished} />
          </RouteView>
          <RouteView tab="compare" active={route === "compare"}>
            <CompareView
              dataset={data.dataset}
              onCountChange={onCompareCount}
            />
          </RouteView>
          <RouteView tab="results" active={route === "results"}>
            <ResultsView
              dataset={data.dataset}
              onCountChange={onResultsCount}
            />
          </RouteView>
          <RouteView tab="analyze" active={route === "analyze"}>
            <AnalyzeView dataset={data.dataset} />
          </RouteView>
        </main>
      </div>
      <div id="drawer-root" />
      <Palette
        items={items}
        open={paletteOpen}
        onSelect={selectPalette}
        onClose={() => setPaletteOpen(false)}
      />
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <AppErrorBoundary>
    <App />
  </AppErrorBoundary>,
);
