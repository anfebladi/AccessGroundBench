export const PROFILES = [
  ["baseline", "Baseline"],
  ["elder_text_heavy", "Text heavy"],
  ["elder_zoom_heavy", "Zoom heavy"],
  ["elder_combo_mid", "Combo mid"],
  ["elder_combo_max", "Combo max"],
  ["colorblind_deuteranomaly", "Deuteranomaly"],
] as const;

export type Profile = (typeof PROFILES)[number][0];
export type Mode = "side-by-side" | "onion";
export type Box = [number, number, number, number];
export type Target = { text: string; baseline_box?: Box };
export type Label = { text?: string | null; box?: Box };
export type Manifest = {
  expected_captures: number;
  successful_captures: number;
  problems?: string[];
};
export type ViewConfig = {
  profile: Profile;
  mode: Mode;
  zoom: "fit" | number;
  evictedOnly: boolean;
  onionPct: number;
};

export const asBox = (v: unknown): Box | undefined =>
  Array.isArray(v) &&
  v.length >= 4 &&
  v.slice(0, 4).every((n) => typeof n === "number" && Number.isFinite(n))
    ? (v.slice(0, 4) as Box)
    : undefined;

export const asText = (v: unknown) =>
  typeof v === "string" && v.trim() ? v.trim() : undefined;

export const ordered = (xs: Target[]) =>
  [...xs].sort(
    (a, b) =>
      (a.baseline_box?.[1] ?? 0) - (b.baseline_box?.[1] ?? 0) ||
      (a.baseline_box?.[0] ?? 0) - (b.baseline_box?.[0] ?? 0),
  );
