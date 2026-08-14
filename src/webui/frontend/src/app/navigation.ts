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

export const routeGroupLabel = (tab: Tab) =>
  ROUTE_GROUPS.find((group) => (group.tabs as readonly Tab[]).includes(tab))!.label;

export const normalizeTab = (value: string): Tab =>
  TABS.includes(value as Tab) ? (value as Tab) : "dataset";
