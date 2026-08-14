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
import type { TabViewProps } from "../../lib/types";
import { CaptureHealth } from "./CaptureHealth";
import { ScreenshotCanvas } from "./ScreenshotCanvas";
import { ComparisonStage } from "./comparison/ComparisonStage";
import { ScreenPicker } from "./ScreenPicker";
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
} from "./types";
export { PROFILES } from "./types";
import { LoadingState } from "../../components/ui/spinner";
import { StageHeader } from "../shared/StageHeader";


export function DatasetView({
  dataset,
  hidden,
}: TabViewProps & {
  dataset: string;
  datasets?: Dataset[];
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
  // One counter per effect. A single shared counter let the screen/profile effect
  // below invalidate this effect's in-flight responses, which pinned
  // initialLoading at true and never mounted the comparison stage.
  const datasetToken = useRef(0);
  const stageToken = useRef(0);
  useEffect(() => {
    if (!dataset) {
      setScreens([]);
      setSelected(null);
      return;
    }
    const t = ++datasetToken.current;
    setInitialLoading(true);
    void Promise.allSettled([
      api<{ screens: string[] }>(`/api/datasets/${enc(dataset)}/screens`),
      api<{ available?: boolean; manifest?: Manifest }>(
        `/api/datasets/${enc(dataset)}/manifest`,
      ),
    ]).then(([screensResult, manifestResult]) => {
      if (t !== datasetToken.current) return;
      const list =
        screensResult.status === "fulfilled"
          ? screensResult.value.screens || []
          : [];
      setScreens(list);
      setSelected(list[0] || null);
      setManifestAvailable(
        manifestResult.status === "fulfilled"
          ? manifestResult.value.available !== false
          : true,
      );
      setManifest(
        manifestResult.status === "fulfilled"
          ? manifestResult.value.manifest || null
          : null,
      );
      setInitialLoading(false);
    });
  }, [dataset]);
  useEffect(() => {
    if (!dataset || !selected) {
      setTargets([]);
      setLabels([]);
      return;
    }
    const t = ++stageToken.current;
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
        if (t !== stageToken.current) return;
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
        if (t !== stageToken.current) return;
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
    <section id="tab-dataset" className="tab min-w-0" aria-labelledby="head-dataset" hidden={hidden}>
      <StageHeader stage="dataset" title="Dataset">
        The screens this benchmark grounds against, captured under each
        accessibility profile.
        <br />
        Check the capture warnings here before you read any number reported
        against this dataset.
      </StageHeader>
      <div id="dataset-warnings">
        <CaptureHealth manifest={manifest} available={manifestAvailable} />
      </div>
      <Card className="rounded-[var(--radius-lg)] border-[var(--border)]">
        <div className="pb-3">
          <h3>Screen comparison</h3>
          <p className="text-sm text-[var(--muted)]">
            Baseline against one accessibility profile, with ground-truth
            boxes.
          </p>
        </div>
        <div className="flex min-w-0 flex-wrap gap-4">
          <ScreenPicker screens={screens} selected={selected} filter={filter} onFilter={setFilter} onSelect={setSelected} />
          <div
            className={`min-w-0 flex-1 transition-opacity ${loading ? "pointer-events-none opacity-45" : ""}`}
            id="screen-browser"
          >
            {initialLoading ? (
              <LoadingState label="Loading dataset" />
            ) : stageError ? (
                <Alert className="border-[var(--danger)]">
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
              <div className="rounded-[var(--radius-md)] border border-dashed p-6 text-center">
                <p className="font-medium">No screen selected</p>
                <p className="mt-1 text-sm text-[var(--muted)]">
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
