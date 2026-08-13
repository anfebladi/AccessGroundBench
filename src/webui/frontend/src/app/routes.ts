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

export const normalizeTab = (value: string): Tab =>
  TABS.includes(value as Tab) ? (value as Tab) : "dataset";

export type PaletteItem = {
  label: string;
  hint: "View" | "Screen" | "Model" | "Action";
  tab: Tab;
  screen?: string;
};
