import { useCallback, useEffect, useState } from "react";
import { api, type Dataset, type Provider } from "../lib/api";
import { normalizeTab, TABS, type Tab } from "./routes";

export function useHashRoute(): [Tab, (tab: Tab) => void] {
  const [route, setRoute] = useState<Tab>(() => normalizeTab(window.location.hash.slice(1)));
  const go = useCallback((tab: Tab) => { window.location.hash = `#${tab}`; }, []);
  useEffect(() => { const onHash = () => setRoute(normalizeTab(window.location.hash.slice(1))); window.addEventListener("hashchange", onHash); return () => window.removeEventListener("hashchange", onHash); }, []);
  useEffect(() => { window.scrollTo?.({ top: 0 }); }, [route]);
  return [route, go];
}

export function useAppData() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [dataset, setDataset] = useState("");
  const [screens, setScreens] = useState<string[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [resultCount, setResultCount] = useState(0);
  const [compareCount, setCompareCount] = useState(0);
  const refresh = useCallback(async () => { const [datasetList, providerList] = await Promise.allSettled([api<Dataset[]>("/api/datasets"), api<Provider[]>("/api/providers")]); if (datasetList.status === "fulfilled") { setDatasets(datasetList.value); setDataset((current) => datasetList.value.some((item) => item.name === current) ? current : (datasetList.value[0]?.name ?? "")); } if (providerList.status === "fulfilled") setProviders(providerList.value); }, []);
  const refreshDatasetData = useCallback(async (name: string) => { const controller = new AbortController(); try { const [screenResult, result] = await Promise.allSettled([api<{ screens: string[] }>(`/api/datasets/${encodeURIComponent(name)}/screens`, { signal: controller.signal }), api<Array<{ filename?: string }>>(`/api/datasets/${encodeURIComponent(name)}/results`, { signal: controller.signal })]); if (screenResult.status === "fulfilled") setScreens(screenResult.value.screens ?? []); if (result.status === "fulfilled") setResultCount(result.value.length); } finally { controller.abort(); } }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => { if (!dataset) { setScreens([]); setResultCount(0); setCompareCount(0); return; } void refreshDatasetData(dataset); }, [dataset, refreshDatasetData]);
  return { datasets, dataset, setDataset, screens, providers, resultCount, setResultCount, compareCount, setCompareCount, refresh, refreshDatasetData };
}

export function useKeyboardPalette(go: (tab: Tab) => void, setOpen: (open: boolean) => void) {
  useEffect(() => { const editable = (target: EventTarget | null) => target instanceof HTMLElement && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT" || target.isContentEditable || target.contentEditable === "true" || Boolean(target.closest('[contenteditable]:not([contenteditable="false"])'))); const onKey = (event: KeyboardEvent) => { const mod = event.metaKey || event.ctrlKey; if (mod && event.key.toLowerCase() === "k") { event.preventDefault(); setOpen(true); return; } if (editable(event.target) || mod || event.altKey) return; const index = Number(event.key); if (index >= 1 && index <= 7) { event.preventDefault(); go(TABS[index - 1]); } if (event.key === "Escape") setOpen(false); }; document.addEventListener("keydown", onKey); return () => document.removeEventListener("keydown", onKey); }, [go, setOpen]);
}
