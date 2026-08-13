export const TABS = [
  "dataset",
  "models",
  "evaluate",
  "collect",
  "compare",
  "results",
  "analyze",
] as const;

export type Tab = (typeof TABS)[number];

export const ROUTE_GROUPS = [
  { label: "Set up", tabs: ["dataset", "models"] as const },
  { label: "Run", tabs: ["evaluate", "collect"] as const },
  { label: "Compare", tabs: ["compare"] as const },
  { label: "Read", tabs: ["results", "analyze"] as const },
] as const;

export const routeLabel = (tab: Tab) => tab[0].toUpperCase() + tab.slice(1);

export const normalizeTab = (value: string): Tab =>
  TABS.includes(value as Tab) ? (value as Tab) : "dataset";

export type PaletteItem = {
  label: string;
  hint: "View" | "Screen" | "Model" | "Action";
  tab: Tab;
  screen?: string;
};
