import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type KeyboardEvent,
} from "react";
import { api, enc, type Dataset, imageUrl, ApiError } from "../../lib/api";
import { imageIsDrawable, strokeWidthFor } from "../../lib/canvas";
import { exportCanvasAsPng } from "../../lib/export";
import {
  deleteView,
  listViews,
  saveView,
  type SavedView,
} from "../../lib/storage";
import type { TabViewProps } from "../../lib/types";
import { CaptureHealth } from "./CaptureHealth";
import { ScreenshotCanvas } from "./ScreenshotCanvas";
import { ComparisonStage } from "./ComparisonStage";
import { ScreenPicker } from "./ScreenPicker";
import { Input } from "../../components/ui/input";
import { Card } from "../../components/ui/card";
import { Alert } from "../../components/ui/alert";
import {
  PROFILES,
  asBox,
  asText,
  ordered,
  type Profile,
  type Box,
  type Target,
  type Label,
  type Manifest,
  type Mode,
  type ViewConfig,
} from "./types";
export { PROFILES } from "./types";
import styles from "./DatasetView.module.css";
import { Skeleton } from "../../components/ui/skeleton";


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
  const [initialLoading, setInitialLoading] = useState(false);
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
    setInitialLoading(true);
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
      })
      .finally(() => { if (t === token.current) setInitialLoading(false); });
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
    <section id="tab-dataset" className={`tab ${styles.root}`} aria-labelledby="head-dataset" hidden={hidden}>
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
      <Card className="card">
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
              <Input
                type="checkbox"
                checked={showBoxes}
                onChange={(e) => setShowBoxes(e.target.checked)}
              />{" "}
              Target boxes
            </label>
            <label className="chip-check">
              <Input
                type="checkbox"
                checked={showMissing}
                onChange={(e) => setShowMissing(e.target.checked)}
              />{" "}
              Missing targets
            </label>
          </div>
        </div>
        <div className="row">
          <ScreenPicker screens={screens} selected={selected} filter={filter} onFilter={setFilter} onSelect={setSelected} />
          <div
            className={`grow ${loading ? "is-loading" : ""}`}
            id="screen-browser"
          >
            {initialLoading ? (
              <div aria-label="Loading dataset">
                <Skeleton className="skeleton-block" />
                <Skeleton className="skeleton-row" />
                <Skeleton className="skeleton-row" />
              </div>
            ) : stageError ? (
              <Alert className="state-error">
                {stageError}
              </Alert>
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
      </Card>
    </section>
  );
}
