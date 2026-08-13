import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type KeyboardEvent,
} from "react";
import { api, enc, type Dataset, imageUrl, ApiError } from "../lib/api";
import { imageIsDrawable, strokeWidthFor } from "../lib/canvas";
import { exportCanvasAsPng } from "../lib/export";
import {
  deleteView,
  listViews,
  saveView,
  type SavedView,
} from "../lib/storage";
import type { TabViewProps } from "../lib/types";
import { CaptureHealth } from "./dataset/CaptureHealth";
import { ScreenshotCanvas } from "./dataset/ScreenshotCanvas";
import { ComparisonStage } from "./dataset/ComparisonStage";

export const PROFILES = [
  ["baseline", "Baseline"],
  ["elder_text_heavy", "Text heavy"],
  ["elder_zoom_heavy", "Zoom heavy"],
  ["elder_combo_mid", "Combo mid"],
  ["elder_combo_max", "Combo max"],
  ["colorblind_deuteranomaly", "Deuteranomaly"],
] as const;
type Profile = (typeof PROFILES)[number][0];
type Mode = "side-by-side" | "onion";
type Box = [number, number, number, number];
type Target = { text: string; baseline_box?: Box };
type Label = { text?: string | null; box?: Box };
type Manifest = {
  expected_captures: number;
  successful_captures: number;
  problems?: string[];
};
type ViewConfig = {
  profile: Profile;
  mode: Mode;
  zoom: "fit" | number;
  evictedOnly: boolean;
  onionPct: number;
};

const asBox = (v: unknown): Box | undefined =>
  Array.isArray(v) &&
  v.length >= 4 &&
  v.slice(0, 4).every((n) => typeof n === "number" && Number.isFinite(n))
    ? (v.slice(0, 4) as Box)
    : undefined;
const asText = (v: unknown) =>
  typeof v === "string" && v.trim() ? v.trim() : undefined;
const ordered = (xs: Target[]) =>
  [...xs].sort(
    (a, b) =>
      (a.baseline_box?.[1] ?? 0) - (b.baseline_box?.[1] ?? 0) ||
      (a.baseline_box?.[0] ?? 0) - (b.baseline_box?.[0] ?? 0),
  );

function Icon({ name }: { name: "download" | "trash" | "bookmark" }) {
  const paths = {
    download: (
      <>
        <path d="M12 3v13M6 11l6 6 6-6" />
        <path d="M4 20h16" />
      </>
    ),
    trash: (
      <>
        <path d="M4 7h16M9 7V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v3M6 7l1 13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-13" />
      </>
    ),
    bookmark: <path d="M6 3h12a1 1 0 0 1 1 1v17l-7-4-7 4V4a1 1 0 0 1 1-1z" />,
  };
  return (
    <svg
      width="13"
      height="13"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}

export function DatasetView({
  dataset,
  screenToSelect,
  hidden,
}: TabViewProps & {
  dataset: string;
  datasets?: Dataset[];
  screenToSelect?: string;
}) {
  const [screens, setScreens] = useState<string[]>([]);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [profile, setProfile] = useState<Profile>("elder_combo_max");
  const [targets, setTargets] = useState<Target[]>([]);
  const [labels, setLabels] = useState<Label[]>([]);
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [manifestAvailable, setManifestAvailable] = useState(true);
  const [loading, setLoading] = useState(false);
  const [stageError, setStageError] = useState("");
  const [showBoxes, setShowBoxes] = useState(true);
  const [showMissing, setShowMissing] = useState(true);
  let token = useRef(0);
  useEffect(() => {
    if (!dataset) {
      setScreens([]);
      setSelected(null);
      return;
    }
    const t = ++token.current;
    void api<{ screens: string[] }>(`/api/datasets/${enc(dataset)}/screens`)
      .then((v) => {
        if (t === token.current) {
          setScreens(v.screens || []);
          setSelected(v.screens?.[0] || null);
        }
      })
      .catch(() => setScreens([]));
    void api<{ available?: boolean; manifest?: Manifest }>(
      `/api/datasets/${enc(dataset)}/manifest`,
    )
      .then((v) => {
        if (t !== token.current) return;
        setManifestAvailable(v.available !== false);
        setManifest(v.manifest || null);
      })
      .catch(() => {
        setManifestAvailable(true);
        setManifest(null);
      });
  }, [dataset]);
  useEffect(() => {
    if (screenToSelect && screens.includes(screenToSelect))
      setSelected(screenToSelect);
  }, [screenToSelect, screens]);
  useEffect(() => {
    if (!dataset || !selected) {
      setTargets([]);
      setLabels([]);
      return;
    }
    const t = ++token.current;
    setLoading(true);
    setStageError("");
    void Promise.all([
      api<{ targets?: unknown }>(
        `/api/datasets/${enc(dataset)}/targets/${enc(selected)}`,
      ),
      api<unknown>(
        `/api/datasets/${enc(dataset)}/labels/${enc(selected)}/${enc(profile)}`,
      ).catch(() => []),
    ])
      .then(([tr, lb]) => {
        if (t !== token.current) return;
        setTargets(
          Array.isArray(tr.targets)
            ? tr.targets.flatMap((x) => {
                if (!x || typeof x !== "object") return [];
                const r = x as { text?: unknown; baseline_box?: unknown };
                const text = asText(r.text);
                return text
                  ? [{ text, baseline_box: asBox(r.baseline_box) }]
                  : [];
              })
            : [],
        );
        setLabels(
          Array.isArray(lb)
            ? lb.flatMap((x) => {
                if (!x || typeof x !== "object") return [];
                const r = x as { text?: unknown; box?: unknown };
                return [{ text: asText(r.text), box: asBox(r.box) }];
              })
            : [],
        );
        setLoading(false);
      })
      .catch((e: unknown) => {
        if (t !== token.current) return;
        setLoading(false);
        setStageError(
          e instanceof ApiError
            ? e.message
            : "Failed to load comparison targets",
        );
      });
  }, [dataset, selected, profile]);
  const visible = screens.filter((s) =>
    s.toLowerCase().includes(filter.trim().toLowerCase()),
  );
  return (
    <section id="tab-dataset" className="tab" aria-labelledby="head-dataset" hidden={hidden}>
      <div className="view-head">
        <h2 id="head-dataset">Dataset</h2>
        <p className="lead">
          The screens this benchmark grounds against, captured under each
          accessibility profile.
          <br />
          Check the capture warnings here before you read any number reported
          against this dataset.
        </p>
      </div>
      <div id="dataset-warnings">
        <CaptureHealth manifest={manifest} available={manifestAvailable} />
      </div>
      <div className="card">
        <div className="card-head">
          <div>
            <h3>Screen comparison</h3>
            <p className="card-sub">
              Baseline against one accessibility profile, with ground-truth
              boxes.
            </p>
          </div>
          <div className="card-head-actions" id="compare-overlay-toggles">
            <label className="chip-check">
              <input
                type="checkbox"
                checked={showBoxes}
                onChange={(e) => setShowBoxes(e.target.checked)}
              />{" "}
              Target boxes
            </label>
            <label className="chip-check">
              <input
                type="checkbox"
                checked={showMissing}
                onChange={(e) => setShowMissing(e.target.checked)}
              />{" "}
              Missing targets
            </label>
          </div>
        </div>
        <div className="row">
          <div className="picker" style={{ flex: "0 0 15rem" }}>
            <input
              id="screen-filter"
              type="search"
              placeholder="Filter screens"
              aria-label="Filter screens"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
            <ul id="screen-list" className="list picker-list">
              {visible.length ? (
                visible.map((s) => (
                  <li
                    data-screen={s}
                    className={s === selected ? "selected" : ""}
                    key={s}
                  >
                    <button
                      type="button"
                      className="screen-picker-button"
                      aria-label={s}
                      onClick={() => setSelected(s)}
                    >
                      {s}
                    </button>
                  </li>
                ))
              ) : (
                <li className="muted" style={{ cursor: "default" }}>
                  No matching screens
                </li>
              )}
            </ul>
          </div>
          <div
            className={`grow ${loading ? "is-loading" : ""}`}
            id="screen-browser"
          >
            {stageError ? (
              <p className="state-error" role="alert">
                {stageError}
              </p>
            ) : selected ? (
              <ComparisonStage
                dataset={dataset}
                screen={selected}
                profile={profile}
                setProfile={setProfile}
                targets={targets}
                labels={labels}
                showBoxes={showBoxes}
                showMissing={showMissing}
                setShowBoxes={setShowBoxes}
                setShowMissing={setShowMissing}
              />
            ) : (
              <div className="empty-state">
                <p className="empty-state-title">No screen selected</p>
                <p className="empty-state-body">
                  Pick a screen from the list to compare its baseline capture
                  against an accessibility profile.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
