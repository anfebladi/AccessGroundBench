import { Component, cloneElement, isValidElement, useCallback, useEffect, useMemo, useState, type ErrorInfo, type ReactElement, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
import { AnalyzeView, CompareView, ResultsView } from "./reporting/views";
import { api, type Dataset, type Model, type Provider, readModels, isTerminalRunStatus } from "./lib/api";
import { CollectView } from "./views/CollectView";
import { DatasetView } from "./views/DatasetView";
import { EvaluateView, type PreflightSummary } from "./views/EvaluateView";
import { ModelsView } from "./views/ModelsView";

export { api, isTerminalRunStatus };

export const TABS = ["dataset", "models", "evaluate", "collect", "compare", "results", "analyze"] as const;
export type Tab = (typeof TABS)[number];
type PaletteItem = { label: string; hint: "View" | "Screen" | "Model" | "Action"; tab: Tab; screen?: string };

export const normalizeTab = (value: string): Tab => TABS.includes(value as Tab) ? value as Tab : "dataset";

const iconPaths: Record<string, ReactNode> = {
  dataset: <><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></>,
  models: <><circle cx="12" cy="12" r="3"/><path d="M12 2v4M12 18v4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M2 12h4M18 12h4M4.9 19.1l2.8-2.8M16.3 7.7l2.8-2.8"/></>,
  evaluate: <><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></>,
  collect: <><rect x="5" y="2" width="14" height="20" rx="2"/><path d="M9 18h.01M9 6h6"/></>,
  results: <><path d="M3 3v18h18"/><rect x="7" y="13" width="3" height="5"/><rect x="12" y="9" width="3" height="9"/><rect x="17" y="5" width="3" height="13"/></>,
  analyze: <><path d="M3 3v18h18"/><path d="M7 15l4-6 3 3 5-8"/></>,
  compare: <><rect x="3" y="4" width="8" height="16" rx="1.5"/><rect x="13" y="4" width="8" height="16" rx="1.5"/><path d="M7 9v6M17 9v6"/></>,
  command: <path d="M9 3a3 3 0 0 0-3 3v12a3 3 0 1 0 3-3h6a3 3 0 1 0-3 3V6a3 3 0 1 0 3 3H9a3 3 0 1 0 3-3z"/>,
};

function Icon({ name, size = 17 }: { name: string; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={size >= 24 ? 1.5 : 2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{iconPaths[name] ?? null}</svg>;
}

type RailProps = { route: Tab; datasets: Dataset[]; dataset: string; models: Model[]; providers: Provider[]; evaluate: PreflightSummary; compareCount: number; resultsCount: number };

function Rail({ route, datasets, dataset, models, providers, evaluate, compareCount, resultsCount }: RailProps) {
  const selected = datasets.find((item) => item.name === dataset);
  const configured = providers.filter((provider) => provider.configured || provider.env_configured || provider.session_configured).length;
  const chips: Record<Tab, string> = {
    dataset: selected ? (selected.is_archived ? "archived, read-only" : `${selected.screen_count} screens`) : "",
    models: models.length ? `${models.length} model${models.length === 1 ? "" : "s"}, ${configured} provider${configured === 1 ? "" : "s"}` : "none configured",
    evaluate: evaluate.text,
    collect: "",
    compare: compareCount ? `${compareCount} model${compareCount === 1 ? "" : "s"}` : "needs results",
    results: resultsCount ? `${resultsCount} result file${resultsCount === 1 ? "" : "s"}` : "no runs yet",
    analyze: resultsCount ? "" : "needs results",
  };
  const groups: Array<{ label: string; tabs: Tab[] }> = [
    { label: "Set up", tabs: ["dataset", "models"] },
    { label: "Run", tabs: ["evaluate", "collect"] },
    { label: "Compare", tabs: ["compare"] },
    { label: "Read", tabs: ["results", "analyze"] },
  ];
  return <nav id="rail" aria-label="Workflow">
    {groups.map(({ label, tabs }) => <div key={label}>
      <p className="rail-group" id={label === "Set up" ? "rail-group-setup" : undefined}>{label}</p>
      {tabs.map((tab) => <a href={`#${tab}`} data-tab={tab} aria-current={route === tab ? "page" : undefined} key={tab}>
        <span className="rail-icon" aria-hidden="true" data-icon={tab}><Icon name={tab}/></span>
        <span className="rail-label">{tab[0].toUpperCase() + tab.slice(1)}</span>
        <span className={`rail-chip${(tab === "evaluate" ? (evaluate.tone === "error" ? " is-err" : evaluate.tone === "info" ? " is-info" : "") : (!chips[tab] && ["models", "compare", "results", "analyze"].includes(tab)) ? " is-warn" : "")}`} data-chip={tab}>{chips[tab]}</span>
      </a>)}
    </div>)}
  </nav>;
}

function useHashRoute(): [Tab, (tab: Tab) => void] {
  const [route, setRoute] = useState<Tab>(() => normalizeTab(window.location.hash.slice(1)));
  const go = useCallback((tab: Tab) => { window.location.hash = `#${tab}`; }, []);
  useEffect(() => {
    const onHash = () => setRoute(normalizeTab(window.location.hash.slice(1)));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  useEffect(() => { window.scrollTo?.({ top: 0 }); }, [route]);
  return [route, go];
}

function Palette({ items, open, onSelect, onClose }: { items: PaletteItem[]; open: boolean; onSelect: (item: PaletteItem) => void; onClose: () => void }) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items.filter((item) => !q || item.label.toLowerCase().includes(q)).sort((a, b) => {
      if (!q) return 0;
      return Number(!a.label.toLowerCase().startsWith(q)) - Number(!b.label.toLowerCase().startsWith(q));
    });
  }, [items, query]);
  useEffect(() => { setActive(0); }, [query, open]);
  useEffect(() => { if (open) document.getElementById("palette-input")?.focus(); }, [open]);
  useEffect(() => { if (open) document.getElementById(`palette-opt-${active}`)?.scrollIntoView?.({ block: "nearest" }); }, [active, open]);
  const keyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") { event.preventDefault(); setActive((value) => Math.min(Math.max(0, filtered.length - 1), value + 1)); }
    else if (event.key === "ArrowUp") { event.preventDefault(); setActive((value) => Math.max(0, value - 1)); }
    else if (event.key === "Enter") { event.preventDefault(); if (filtered[active]) onSelect(filtered[active]); }
    else if (event.key === "Escape") onClose();
  };
  return <div className="palette-backdrop" id="palette-backdrop" hidden={!open} onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="palette" role="dialog" aria-modal="true" aria-label="Command palette">
      <div className="palette-input-row"><input autoComplete="off" type="text" id="palette-input" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={keyDown} role="combobox" aria-expanded="true" aria-controls="palette-list" aria-autocomplete="list" aria-activedescendant={filtered.length ? `palette-opt-${active}` : undefined} placeholder="Jump to a view, screen, or model…" /></div>
      <ul id="palette-list" role="listbox" aria-label="Results">
        {filtered.length ? filtered.map((item, index) => <li role="option" id={`palette-opt-${index}`} className={index === active ? "is-active" : ""} aria-selected={index === active} key={`${item.hint}-${item.label}`} onClick={() => onSelect(item)}><span className="palette-item-label">{item.label}</span><span className="palette-item-hint">{item.hint}</span></li>) : <li className="palette-empty muted small">No matches</li>}
      </ul>
      <div className="palette-foot"><span><kbd>↑</kbd><kbd>↓</kbd> navigate</span><span><kbd>Enter</kbd> select</span><span><kbd>Esc</kbd> close</span><span><kbd>1</kbd>–<kbd>7</kbd> jump to a view</span></div>
    </div>
  </div>;
}

type ErrorState = { hasError: boolean; message: string };
class AppErrorBoundary extends Component<{ children: ReactNode }, ErrorState> {
  state: ErrorState = { hasError: false, message: "" };
  static getDerivedStateFromError(error: unknown): ErrorState { return { hasError: true, message: error instanceof Error ? error.message : "The interface encountered an unexpected error." }; }
  componentDidCatch(error: unknown, _info: ErrorInfo) { console.error("AccessGroundBench UI failed to render", error); }
  render() { return this.state.hasError ? <main className="app-error" role="alert" aria-live="assertive"><h1>AccessGroundBench could not render this view</h1><p>Refresh the page and try again. If the problem persists, check the dataset response and browser console.</p>{this.state.message && <p className="note note-warn">{this.state.message}</p>}<button type="button" className="secondary" onClick={() => window.location.reload()}>Reload interface</button></main> : this.props.children; }
}

function RouteView({ tab, active, children }: { tab: Tab; active: boolean; children: ReactNode }) {
  if (!isValidElement(children)) return null;
  return cloneElement(children as ReactElement<{ hidden?: boolean }>, { hidden: !active });
}

export function App() {
  const [route, go] = useHashRoute();
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [dataset, setDataset] = useState("");
  const [screens, setScreens] = useState<string[]>([]);
  const [models, setModels] = useState<Model[]>(readModels);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [resultCount, setResultCount] = useState(0);
  const [compareCount, setCompareCount] = useState(0);
  const [evaluateSummary, setEvaluateSummary] = useState<PreflightSummary>({ text: "", tone: "muted" });
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [paletteScreen, setPaletteScreen] = useState<string>();

  const refresh = useCallback(async () => {
    const [datasetList, providerList] = await Promise.allSettled([api<Dataset[]>("/api/datasets"), api<Provider[]>("/api/providers")]);
    if (datasetList.status === "fulfilled") { setDatasets(datasetList.value); setDataset((current) => datasetList.value.some((item) => item.name === current) ? current : datasetList.value[0]?.name ?? ""); }
    if (providerList.status === "fulfilled") setProviders(providerList.value);
  }, []);
  const refreshDatasetData = useCallback(async (name: string) => {
    const controller = new AbortController();
    try {
      const [screenResult, result] = await Promise.allSettled([
        api<{ screens: string[] }>(`/api/datasets/${encodeURIComponent(name)}/screens`, { signal: controller.signal }),
        api<Array<{ filename?: string }>>(`/api/datasets/${encodeURIComponent(name)}/results`, { signal: controller.signal }),
      ]);
      if (screenResult.status === "fulfilled") setScreens(screenResult.value.screens ?? []);
      if (result.status === "fulfilled") setResultCount(result.value.length);
    } finally { controller.abort(); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => { if (!dataset) { setScreens([]); setResultCount(0); setCompareCount(0); return; } void refreshDatasetData(dataset); }, [dataset, refreshDatasetData]);

  const items = useMemo<PaletteItem[]>(() => [
    ...TABS.map((tab) => ({ label: tab[0].toUpperCase() + tab.slice(1), hint: "View" as const, tab })),
    ...screens.map((screen) => ({ label: screen, hint: "Screen" as const, tab: "dataset" as Tab, screen })),
    ...models.map((model) => ({ label: model.id, hint: "Model" as const, tab: "models" as Tab })),
    ...([ ["Run an evaluation", "evaluate"], ["Run an analysis", "analyze"], ["Compare a model against baseline", "compare"], ["Collect a new dataset", "collect"] ] as const).map(([label, tab]) => ({ label, hint: "Action" as const, tab })),
  ], [models, screens]);
  const selectPalette = (item: PaletteItem) => { if (item.screen) setPaletteScreen(item.screen); go(item.tab); setPaletteOpen(false); };
  useEffect(() => {
    const editable = (target: EventTarget | null) => target instanceof HTMLElement && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT" || target.isContentEditable || target.contentEditable === "true" || Boolean(target.closest('[contenteditable]:not([contenteditable="false"])')));
    const onKey = (event: KeyboardEvent) => { const mod = event.metaKey || event.ctrlKey; if (mod && event.key.toLowerCase() === "k") { event.preventDefault(); setPaletteOpen(true); return; } if (editable(event.target) || mod || event.altKey) return; const index = Number(event.key); if (index >= 1 && index <= 7) { event.preventDefault(); go(TABS[index - 1]); } if (event.key === "Escape") setPaletteOpen(false); };
    document.addEventListener("keydown", onKey); return () => document.removeEventListener("keydown", onKey);
  }, [go]);
  const onEvaluateSummary = useCallback((summary: PreflightSummary) => setEvaluateSummary((current) => current.text === summary.text && current.tone === summary.tone ? current : summary), []);
  const onCompareCount = useCallback((count: number) => setCompareCount((current) => current === count ? current : count), []);
  const onResultsCount = useCallback((count: number) => setResultCount((current) => current === count ? current : count), []);

  return <>
    <header className="app-header"><div className="brand"><span className="brand-mark" aria-hidden="true">AGB</span><span className="brand-name">AccessGroundBench</span></div><div className="header-controls"><label htmlFor="dataset-select">Dataset</label><select id="dataset-select" value={dataset} onChange={(event) => setDataset(event.target.value)}>{!datasets.length && <option value="">Select dataset</option>}{datasets.map((item) => <option key={item.name} value={item.name}>{item.is_archived ? `${item.name} (archived)` : item.name}</option>)}</select><span id="dataset-meta" className="meta">{datasets.find((item) => item.name === dataset) ? `${datasets.find((item) => item.name === dataset)!.screen_count} screens, ${datasets.find((item) => item.name === dataset)!.image_count} images${datasets.find((item) => item.name === dataset)!.is_archived ? " -- archived, read-only" : ""}` : ""}</span><button type="button" className="secondary small icon-btn" id="palette-trigger" data-icon="command" title="Command palette (Ctrl/Cmd+K)" aria-label="Open command palette" onClick={() => setPaletteOpen(true)}><Icon name="command" /></button></div></header>

    <div className="app-body"><Rail route={route} datasets={datasets} dataset={dataset} models={models} providers={providers} evaluate={evaluateSummary} compareCount={compareCount} resultsCount={resultCount}/><main>
      <RouteView tab="dataset" active={route === "dataset"}><DatasetView dataset={dataset} datasets={datasets} screenToSelect={paletteScreen}/></RouteView>
      <RouteView tab="models" active={route === "models"}><ModelsView onChange={setModels} dataset={dataset} screen={screens[0]}/></RouteView>
      <RouteView tab="evaluate" active={route === "evaluate"}><EvaluateView dataset={dataset} models={models} onPreflightSummary={onEvaluateSummary} onRunFinished={() => { void refresh(); if (dataset) void refreshDatasetData(dataset); }}/></RouteView>
      <RouteView tab="collect" active={route === "collect"}><CollectView onRunFinished={() => { void refresh(); if (dataset) void refreshDatasetData(dataset); }}/></RouteView>
      <RouteView tab="compare" active={route === "compare"}><CompareView dataset={dataset} onCountChange={onCompareCount}/></RouteView>
      <RouteView tab="results" active={route === "results"}><ResultsView dataset={dataset} onCountChange={onResultsCount}/></RouteView>
      <RouteView tab="analyze" active={route === "analyze"}><AnalyzeView dataset={dataset}/></RouteView>
    </main></div><div id="drawer-root"/><Palette items={items} open={paletteOpen} onSelect={selectPalette} onClose={() => setPaletteOpen(false)}/>
  </>;
}

createRoot(document.getElementById("root")!).render(<AppErrorBoundary><App /></AppErrorBoundary>);
