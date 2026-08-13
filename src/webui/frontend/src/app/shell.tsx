import { Component, cloneElement, isValidElement, useEffect, useMemo, useState, type ErrorInfo, type ReactElement, type ReactNode } from "react";
import type { Dataset, Model, Provider } from "../lib/api";
import type { PreflightSummary } from "../views/EvaluateView";
import type { PaletteItem, Tab } from "./routes";
import { Icon } from "./icons";

export function Header({ datasets, dataset, onDatasetChange, onPalette }: { datasets: Dataset[]; dataset: string; onDatasetChange: (value: string) => void; onPalette: () => void }) {
  const selected = datasets.find((item) => item.name === dataset);
  return <header className="app-header"><div className="brand"><span className="brand-mark" aria-hidden="true">AGB</span><span className="brand-name">AccessGroundBench</span></div><div className="header-controls"><label htmlFor="dataset-select">Dataset</label><select id="dataset-select" value={dataset} onChange={(event) => onDatasetChange(event.target.value)}>{!datasets.length && <option value="">Select dataset</option>}{datasets.map((item) => <option key={item.name} value={item.name}>{item.is_archived ? `${item.name} (archived)` : item.name}</option>)}</select><span id="dataset-meta" className="meta">{selected ? `${selected.screen_count} screens, ${selected.image_count} images${selected.is_archived ? " -- archived, read-only" : ""}` : ""}</span><button type="button" className="secondary small icon-btn" id="palette-trigger" data-icon="command" title="Command palette (Ctrl/Cmd+K)" aria-label="Open command palette" onClick={onPalette}><Icon name="command" /></button></div></header>;
}

export function Rail({ route, datasets, dataset, models, providers, evaluate, compareCount, resultsCount }: { route: Tab; datasets: Dataset[]; dataset: string; models: Model[]; providers: Provider[]; evaluate: PreflightSummary; compareCount: number; resultsCount: number }) {
  const selected = datasets.find((item) => item.name === dataset);
  const configured = providers.filter((provider) => provider.configured || provider.env_configured || provider.session_configured).length;
  const chips: Record<Tab, string> = { dataset: selected ? selected.is_archived ? "archived, read-only" : `${selected.screen_count} screens` : "", models: models.length ? `${models.length} model${models.length === 1 ? "" : "s"}, ${configured} provider${configured === 1 ? "" : "s"}` : "none configured", evaluate: evaluate.text, collect: "", compare: compareCount ? `${compareCount} model${compareCount === 1 ? "" : "s"}` : "needs results", results: resultsCount ? `${resultsCount} result file${resultsCount === 1 ? "" : "s"}` : "no runs yet", analyze: resultsCount ? "" : "needs results" };
  const groups: Array<{ label: string; tabs: Tab[] }> = [{ label: "Set up", tabs: ["dataset", "models"] }, { label: "Run", tabs: ["evaluate", "collect"] }, { label: "Compare", tabs: ["compare"] }, { label: "Read", tabs: ["results", "analyze"] }];
  return <nav id="rail" aria-label="Workflow">{groups.map(({ label, tabs }) => <div key={label}><p className="rail-group" id={label === "Set up" ? "rail-group-setup" : undefined}>{label}</p>{tabs.map((tab) => <a href={`#${tab}`} data-tab={tab} aria-current={route === tab ? "page" : undefined} key={tab}><span className="rail-icon" aria-hidden="true" data-icon={tab}><Icon name={tab} /></span><span className="rail-label">{tab[0].toUpperCase() + tab.slice(1)}</span><span className={`rail-chip${tab === "evaluate" ? (evaluate.tone === "error" ? " is-err" : evaluate.tone === "info" ? " is-info" : "") : !chips[tab] && ["models", "compare", "results", "analyze"].includes(tab) ? " is-warn" : ""}`} data-chip={tab}>{chips[tab]}</span></a>)}</div>)}</nav>;
}

export function Palette({ items, open, onSelect, onClose }: { items: PaletteItem[]; open: boolean; onSelect: (item: PaletteItem) => void; onClose: () => void }) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const filtered = useMemo(() => { const q = query.trim().toLowerCase(); return items.filter((item) => !q || item.label.toLowerCase().includes(q)).sort((a, b) => q ? Number(!a.label.toLowerCase().startsWith(q)) - Number(!b.label.toLowerCase().startsWith(q)) : 0); }, [items, query]);
  useEffect(() => setActive(0), [query, open]);
  useEffect(() => { if (open) document.getElementById("palette-input")?.focus(); }, [open]);
  useEffect(() => { if (open) document.getElementById(`palette-opt-${active}`)?.scrollIntoView?.({ block: "nearest" }); }, [active, open]);
  const keyDown = (event: React.KeyboardEvent<HTMLInputElement>) => { if (event.key === "ArrowDown") { event.preventDefault(); setActive((value) => Math.min(Math.max(0, filtered.length - 1), value + 1)); } else if (event.key === "ArrowUp") { event.preventDefault(); setActive((value) => Math.max(0, value - 1)); } else if (event.key === "Enter") { event.preventDefault(); if (filtered[active]) onSelect(filtered[active]); } else if (event.key === "Escape") onClose(); };
  return <div className="palette-backdrop" id="palette-backdrop" hidden={!open} onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}><div className="palette" role="dialog" aria-modal="true" aria-label="Command palette"><div className="palette-input-row"><input autoComplete="off" type="text" id="palette-input" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={keyDown} role="combobox" aria-expanded="true" aria-controls="palette-list" aria-autocomplete="list" aria-activedescendant={filtered.length ? `palette-opt-${active}` : undefined} placeholder="Jump to a view, screen, or model…" /></div><ul id="palette-list" role="listbox" aria-label="Results">{filtered.length ? filtered.map((item, index) => <li role="option" id={`palette-opt-${index}`} className={index === active ? "is-active" : ""} aria-selected={index === active} key={`${item.hint}-${item.label}`} onClick={() => onSelect(item)}><span className="palette-item-label">{item.label}</span><span className="palette-item-hint">{item.hint}</span></li>) : <li className="palette-empty muted small">No matches</li>}</ul><div className="palette-foot"><span><kbd>↑</kbd><kbd>↓</kbd> navigate</span><span><kbd>Enter</kbd> select</span><span><kbd>Esc</kbd> close</span><span><kbd>1</kbd>–<kbd>7</kbd> jump to a view</span></div></div></div>;
}

export class AppErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean; message: string }> {
  state = { hasError: false, message: "" };
  static getDerivedStateFromError(error: unknown) { return { hasError: true, message: error instanceof Error ? error.message : "The interface encountered an unexpected error." }; }
  componentDidCatch(error: unknown, _info: ErrorInfo) { console.error("AccessGroundBench UI failed to render", error); }
  render() { return this.state.hasError ? <main className="app-error" role="alert" aria-live="assertive"><h1>AccessGroundBench could not render this view</h1><p>Refresh the page and try again. If the problem persists, check the dataset response and browser console.</p>{this.state.message && <p className="note note-warn">{this.state.message}</p>}<button type="button" className="secondary" onClick={() => window.location.reload()}>Reload interface</button></main> : this.props.children; }
}

export function RouteView({ tab: _tab, active, children }: { tab: Tab; active: boolean; children: ReactNode }) { if (!isValidElement(children)) return null; return cloneElement(children as ReactElement<{ hidden?: boolean }>, { hidden: !active }); }
