import { useCallback, useMemo, useState } from "react";
import { api, isTerminalRunStatus, readModels, type Model } from "../lib/api";
import { AnalyzeView } from "../features/analyze/AnalyzeView";
import { CompareView } from "../features/compare/CompareView";
import { ResultsView } from "../features/results/ResultsView";
import { CollectView } from "../features/collect/CollectView";
import { DatasetView } from "../features/dataset/DatasetView";
import { EvaluateView } from "../features/evaluate/EvaluateView";
import { ModelsView } from "../features/models/ModelsView";
import { AppShell } from "../components/shell/AppShell";
import { CommandPalette } from "../components/shell/CommandPalette";
import { PageOutlet } from "../components/shell/PageOutlet";
import { useAppData } from "./hooks/useAppData";
import { useHashRoute } from "./hooks/useHashRoute";
import { useKeyboardPalette } from "./hooks/useKeyboardPalette";
import type { PaletteItem, Tab } from "./navigation";
import { TABS } from "./navigation";
import type { PreflightSummary } from "../lib/types";

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
  const onRunFinished = () => {
    void data.refresh();
    if (data.dataset) void data.refreshDatasetData(data.dataset);
  };
  return (
    <>
      <AppShell
        route={route}
        datasets={data.datasets}
        dataset={data.dataset}
        models={models}
        providers={data.providers}
        evaluate={evaluateSummary}
        compareCount={data.compareCount}
        resultsCount={data.resultCount}
        onDatasetChange={data.setDataset}
        onPalette={() => setPaletteOpen(true)}
        dataLoading={data.loading || data.datasetLoading}
      >
        <PageOutlet active={route === "dataset"}>
          <DatasetView
            dataset={data.dataset}
            datasets={data.datasets}
            screenToSelect={paletteScreen}
          />
        </PageOutlet>
        <PageOutlet active={route === "models"}>
          <ModelsView
            onChange={setModels}
            onProvidersChange={data.setProviders}
            dataset={data.dataset}
            screen={data.screens[0]}
          />
        </PageOutlet>
        <PageOutlet active={route === "evaluate"}>
          <EvaluateView
            dataset={data.dataset}
            models={models}
            onPreflightSummary={setEvaluateSummary}
            onRunFinished={onRunFinished}
          />
        </PageOutlet>
        <PageOutlet active={route === "collect"}>
          <CollectView onRunFinished={onRunFinished} />
        </PageOutlet>
        <PageOutlet active={route === "compare"}>
          <CompareView
            dataset={data.dataset}
            onCountChange={data.setCompareCount}
          />
        </PageOutlet>
        <PageOutlet active={route === "results"}>
          <ResultsView
            dataset={data.dataset}
            onCountChange={data.setResultCount}
          />
        </PageOutlet>
        <PageOutlet active={route === "analyze"}>
          <AnalyzeView dataset={data.dataset} />
        </PageOutlet>
      </AppShell>
      <div id="drawer-root" />
      <CommandPalette
        items={items}
        open={paletteOpen}
        onSelect={selectPalette}
        onClose={() => setPaletteOpen(false)}
      />
    </>
  );
}
