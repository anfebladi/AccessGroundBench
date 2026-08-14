import { useCallback, useState } from "react";
import { api, isTerminalRunStatus, readModels, type Model } from "../lib/api";
import { AnalyzeView } from "../features/analyze/AnalyzeView";
import { CompareView } from "../features/compare/CompareView";
import { ResultsView } from "../features/results/ResultsView";
import { CollectView } from "../features/collect/CollectView";
import { DatasetView } from "../features/dataset/DatasetView";
import { EvaluateView } from "../features/evaluate/EvaluateView";
import { ModelsView } from "../features/models/ModelsView";
import { AppShell } from "../components/shell/AppShell";
import { PageOutlet } from "../components/shell/PageOutlet";
import { useAppData } from "./hooks/useAppData";
import { useHashRoute } from "./hooks/useHashRoute";
import { useKeyboardShortcuts } from "./hooks/useKeyboardShortcuts";
import type { PreflightSummary } from "../lib/types";

export function App() {
  const [route, go] = useHashRoute();
  const data = useAppData();
  const [models, setModels] = useState<Model[]>(readModels);
  const [evaluateSummary, setEvaluateSummary] = useState<PreflightSummary>({
    text: "",
    tone: "muted",
  });
  useKeyboardShortcuts(go);
  const onRunFinished = () => {
    void data.refresh();
    if (data.dataset) void data.refreshDatasetData(data.dataset);
  };
  return (
    <>
      <AppShell
        route={route}
        datasets={data.datasets}
        datasetsError={data.datasetsError}
        dataset={data.dataset}
        models={models}
        providers={data.providers}
        evaluate={evaluateSummary}
        compareCount={data.compareCount}
        resultsCount={data.resultCount}
        onDatasetChange={data.setDataset}
        dataLoading={data.loading || data.datasetLoading}
      >
        <PageOutlet active={route === "dataset"}>
          <DatasetView
            dataset={data.dataset}
            datasets={data.datasets}
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
    </>
  );
}
