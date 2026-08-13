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

function CaptureHealth({
  manifest,
  available,
}: {
  manifest: Manifest | null;
  available: boolean;
}) {
  if (!available)
    return (
      <div className="note note-warn">
        <span className="note-label">Warning</span>No{" "}
        <code>collection_manifest.json</code> for this dataset, so capture
        completeness and content drift are unknown.
      </div>
    );
  if (!manifest) return null;
  const complete = manifest.expected_captures === manifest.successful_captures;
  const problems = manifest.problems || [];
  return (
    <div className="card">
      <div className="card-head">
        <div>
          <h3>Capture health</h3>
          <p className="card-sub">
            Read this before trusting any number reported against this dataset.
          </p>
        </div>
        <div className="card-head-actions">
          <span className={`badge ${complete ? "ok" : "err"}`}>
            {manifest.successful_captures}/{manifest.expected_captures} captures{" "}
            {complete ? "complete" : "-- incomplete"}
          </span>
        </div>
      </div>
      {problems.length ? (
        <div className="note note-warn">
          <span className="note-label">Warning</span>
          <b>
            {problems.length} warning{problems.length === 1 ? "" : "s"}
          </b>{" "}
          -- affected screens carry a caveat, they are not automatically
          excluded.
          <ul>
            {problems.map((p, i) => (
              <li key={`${i}-${p}`}>{p}</li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="muted small">
          No drift or contamination warnings recorded.
        </p>
      )}
    </div>
  );
}

function ScreenshotCanvas({
  dataset,
  screen,
  profile,
  targets,
  present,
  missing,
  labels,
  selected,
  showBoxes,
  showMissing,
  evictedOnly,
  zoom,
  onSelect,
  id,
  wrapperRef,
  hidden,
  className,
  onDimensions,
  onCanvasReady,
}: {
  dataset: string;
  screen: string;
  profile: string;
  targets: Target[];
  present: Set<string>;
  missing: Target[];
  labels: Label[];
  selected: string | null;
  showBoxes: boolean;
  showMissing: boolean;
  evictedOnly: boolean;
  zoom: "fit" | number;
  onSelect: (text: string) => void;
  id: string;
  wrapperRef: React.RefObject<HTMLDivElement | null>;
  hidden?: boolean;
  className?: string;
  onDimensions?: (value: string) => void;
  onCanvasReady?: (canvas: HTMLCanvasElement) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [img, setImg] = useState<HTMLImageElement | null>(null);
  const [dims, setDims] = useState(" ");
  useEffect(() => {
    const image = new Image();
    image.onload = () => setImg(image);
    image.onerror = () => setImg(image);
    image.src = imageUrl(dataset, screen, profile);
    return () => {
      image.onload = null;
      image.onerror = null;
    };
  }, [dataset, screen, profile]);
  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapperRef.current;
    if (!canvas || !img) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    if (!imageIsDrawable(img)) {
      canvas.width = 400;
      canvas.height = 80;
      ctx.clearRect(0, 0, 400, 80);
      ctx.fillStyle = "#b3221a";
      ctx.font = "14px sans-serif";
      ctx.fillText("Screenshot not available", 12, 44);
      setDims("—");
      onDimensions?.("—");
      return;
    }
    canvas.width = img.width;
    canvas.height = img.height;
    ctx.drawImage(img, 0, 0);
    setDims(`${img.width} x ${img.height}`);
    onDimensions?.(`${img.width} x ${img.height}`);
    if (!showBoxes) return;
    const sw = strokeWidthFor(img),
      accent = "#2a78d6",
      err = "#b3221a",
      warn = "#a15c00";
    const draw = (
      text: string | undefined,
      b: Box | undefined,
      color: string,
    ) => {
      if (!b) return;
      ctx.strokeStyle = text === selected ? warn : color;
      ctx.lineWidth = text === selected ? sw * 1.6 : sw;
      ctx.strokeRect(b[0], b[1], b[2] - b[0], b[3] - b[1]);
    };
    if (profile === "baseline") {
      if (!evictedOnly)
        targets
          .filter((t) => present.has(t.text))
          .forEach((t) => draw(t.text, t.baseline_box, accent));
      if (showMissing || evictedOnly)
        missing.forEach((t) => draw(t.text, t.baseline_box, err));
    } else if (!evictedOnly)
      labels.forEach((l) => {
        const text = asText(l.text);
        if (text && present.has(text)) draw(text, l.box, accent);
      });
  }, [
    img,
    targets,
    present,
    missing,
    labels,
    selected,
    showBoxes,
    showMissing,
    evictedOnly,
    zoom,
    wrapperRef,
    profile,
    onDimensions,
  ]);
  useEffect(() => {
    if (canvasRef.current) onCanvasReady?.(canvasRef.current);
  }, [onCanvasReady]);
  const style: React.CSSProperties = {};
  if (zoom !== "fit" && img && imageIsDrawable(img)) {
    style.width = `${Math.round(img.width * zoom)}px`;
    style.height = `${Math.round(img.height * zoom)}px`;
  }
  return (
    <canvas
      id={`canvas-${id}`}
      ref={canvasRef}
      hidden={hidden}
      className={className}
      style={style}
      onClick={(e) => {
        if (!img || !imageIsDrawable(img)) return;
        const rect = e.currentTarget.getBoundingClientRect();
        const x = ((e.clientX - rect.left) / rect.width) * img.width;
        const y = ((e.clientY - rect.top) / rect.height) * img.height;
        const hit = (evictedOnly ? missing : targets).find((t) => {
          const b = t.baseline_box;
          return b && x >= b[0] && x <= b[2] && y >= b[1] && y <= b[3];
        });
        if (hit) onSelect(hit.text);
      }}
    />
  );
}

function ComparisonStage({
  dataset,
  screen,
  profile,
  setProfile,
  targets,
  labels,
  showBoxes,
  showMissing,
  setShowBoxes,
  setShowMissing,
}: {
  dataset: string;
  screen: string;
  profile: Profile;
  setProfile: (p: Profile) => void;
  targets: Target[];
  labels: Label[];
  showBoxes: boolean;
  showMissing: boolean;
  setShowBoxes: (v: boolean) => void;
  setShowMissing: (v: boolean) => void;
}) {
  const [mode, setMode] = useState<Mode>("side-by-side");
  const [zoom, setZoom] = useState<"fit" | number>("fit");
  const [evictedOnly, setEvictedOnly] = useState(false);
  const [onionPct, setOnionPct] = useState(50);
  const [selected, setSelected] = useState<string | null>(null);
  const [saved, setSaved] =
    useState<SavedView<ViewConfig>[]>(listViews<ViewConfig>());
  const [viewName, setViewName] = useState("");
  const [chosenView, setChosenView] = useState("");
  const [baseDims, setBaseDims] = useState(""),
    [profileDims, setProfileDims] = useState("");
  const baseWrap = useRef<HTMLDivElement>(null);
  const profileWrap = useRef<HTMLDivElement>(null);
  const onionWrap = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);
  useEffect(() => {
    const update = () => {
      const a = baseWrap.current?.querySelector("canvas");
      const b = profileWrap.current?.querySelector("canvas");
      if (a?.width) setBaseDims(`${a.width} x ${a.height}`);
      if (b?.width) setProfileDims(`${b.width} x ${b.height}`);
    };
    const id = window.setInterval(update, 100);
    update();
    return () => window.clearInterval(id);
  }, [dataset, screen, profile, mode, zoom]);
  const present = useMemo(
    () =>
      new Set(
        labels
          .map((x) => asText(x.text))
          .filter((x): x is string => Boolean(x)),
      ),
    [labels],
  );
  const missing = useMemo(
    () => targets.filter((t) => !present.has(t.text)),
    [targets, present],
  );
  const list = ordered(evictedOnly ? missing : targets);
  const label = PROFILES.find((p) => p[0] === profile)?.[1] || profile;
  const isBaseline = profile === "baseline";
  const setSelection = (text: string) =>
    setSelected((v) => (v === text ? null : text));
  const changeZoom = (action: string) => {
    if (action === "fit") return setZoom("fit");
    if (action === "1:1") return setZoom(1);
    const current = zoom === "fit" ? 1 : zoom;
    setZoom(
      Math.max(0.25, Math.min(4, current + (action === "in" ? 0.25 : -0.25))),
    );
  };
  const applyView = (name: string) => {
    const view = saved.find((x) => x.name === name);
    if (!view) return;
    const c = view.config;
    setMode(c.mode === "onion" ? "onion" : "side-by-side");
    setZoom(c.zoom);
    setEvictedOnly(Boolean(c.evictedOnly));
    setOnionPct(Number.isFinite(c.onionPct) ? c.onionPct : 50);
    if (c.profile !== profile) setProfile(c.profile);
  };
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (
      e.target instanceof HTMLElement &&
      (e.target.closest("#stage-target-list") ||
        e.target.closest("#onion-divider"))
    )
      return;
    if (
      ![
        "j",
        "k",
        "ArrowLeft",
        "ArrowRight",
        "ArrowUp",
        "ArrowDown",
        "+",
        "=",
        "-",
      ].includes(e.key)
    )
      return;
    e.preventDefault();
    if (e.key === "+" || e.key === "=") return changeZoom("in");
    if (e.key === "-") return changeZoom("out");
    if (e.key.startsWith("Arrow")) {
      const dx = e.key === "ArrowLeft" ? -80 : e.key === "ArrowRight" ? 80 : 0;
      const dy = e.key === "ArrowUp" ? -80 : e.key === "ArrowDown" ? 80 : 0;
      [baseWrap.current, profileWrap.current, onionWrap.current].forEach((r) =>
        r?.scrollBy({ left: dx, top: dy }),
      );
      return;
    }
    const i = list.findIndex((x) => x.text === selected);
    const next =
      e.key === "j"
        ? list[Math.min(list.length - 1, i + 1)]
        : list[Math.max(0, i <= 0 ? 0 : i - 1)];
    if (next) setSelection(next.text);
  };
  const onDividerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!dragging.current) return;
    const rect = e.currentTarget.parentElement?.getBoundingClientRect();
    if (rect)
      setOnionPct(
        Math.max(
          0,
          Math.min(100, ((e.clientX - rect.left) / rect.width) * 100),
        ),
      );
  };
  const saveCurrent = () => {
    const name = viewName.trim();
    if (!name) return;
    setSaved(
      saveView<ViewConfig>(name, {
        profile,
        mode,
        zoom,
        evictedOnly,
        onionPct,
      }),
    );
    setViewName("");
  };
  return (
    <div onKeyDown={onKeyDown}>
      <div
        className="segmented"
        id="profile-picker"
        role="group"
        aria-label="Accessibility profile"
      >
        {PROFILES.map(([id, text]) => (
          <button
            type="button"
            key={id}
            aria-pressed={id === profile}
            onClick={() => setProfile(id)}
          >
            {text}
          </button>
        ))}
      </div>
      <div className="stage-toolbar">
        <div
          className="segmented"
          id="stage-mode-picker"
          role="group"
          aria-label="Comparison mode"
        >
          <button
            type="button"
            aria-pressed={mode === "side-by-side"}
            onClick={() => setMode("side-by-side")}
          >
            Side by side
          </button>
          <button
            type="button"
            aria-pressed={mode === "onion"}
            onClick={() => setMode("onion")}
          >
            Onion-skin
          </button>
        </div>
        <div
          className="segmented"
          id="stage-zoom"
          role="group"
          aria-label="Zoom"
        >
          <button
            type="button"
            onClick={() => changeZoom("out")}
            aria-label="Zoom out"
          >
            −
          </button>
          <button
            type="button"
            onClick={() => changeZoom("fit")}
            aria-pressed={zoom === "fit"}
          >
            Fit
          </button>
          <button
            type="button"
            onClick={() => changeZoom("1:1")}
            aria-pressed={zoom === 1}
          >
            1:1
          </button>
          <button
            type="button"
            onClick={() => changeZoom("in")}
            aria-label="Zoom in"
          >
            +
          </button>
        </div>
        <label className="chip-check">
          <input
            type="checkbox"
            checked={evictedOnly}
            onChange={(e) => setEvictedOnly(e.target.checked)}
          />{" "}
          Evicted only
        </label>
      </div>
      <div className="stage-toolbar" style={{ marginTop: "var(--space-2)" }}>
        <select
          id="stage-saved-views"
          aria-label="Saved views"
          value={chosenView}
          onChange={(e) => {
            setChosenView(e.target.value);
            applyView(e.target.value);
          }}
        >
          <option value="">Saved views…</option>
          {saved.map((v) => (
            <option value={v.name} key={v.name}>
              {v.name}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="secondary small icon-btn"
          id="stage-view-delete"
          disabled={!chosenView}
          title="Delete saved view"
          aria-label="Delete saved view"
          onClick={() => {
            if (chosenView) {
              setSaved(deleteView(chosenView) as SavedView<ViewConfig>[]);
              setChosenView("");
            }
          }}
        >
          <Icon name="trash" />
        </button>
        <input
          type="text"
          id="stage-view-name"
          placeholder="Name this view"
          style={{ maxWidth: "12rem" }}
          value={viewName}
          onChange={(e) => setViewName(e.target.value)}
        />
        <button
          type="button"
          className="secondary small icon-btn"
          id="stage-view-save"
          title="Save current view"
          aria-label="Save current view"
          onClick={saveCurrent}
        >
          <Icon name="bookmark" />
        </button>
      </div>
      <div className="stage-body">
        <div
          className="stage-targets"
          id="stage-target-list"
          role="listbox"
          aria-label="Groundable targets"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
            e.preventDefault();
            const i = list.findIndex((x) => x.text === selected);
            const n =
              e.key === "ArrowDown"
                ? Math.min(list.length - 1, i + 1)
                : Math.max(0, i <= 0 ? 0 : i - 1);
            if (list[n]) setSelected(list[n].text);
          }}
        >
          {list.length ? (
            list.map((t) => (
              <button
                type="button"
                className={`stage-target-item${missing.some((m) => m.text === t.text) ? " is-missing" : ""}${selected === t.text ? " is-selected" : ""}`}
                aria-selected={selected === t.text}
                key={t.text}
                onClick={() => setSelection(t.text)}
              >
                <span className="stage-target-dot" aria-hidden="true" />
                <span className="stage-target-text">{t.text}</span>
                {missing.some((m) => m.text === t.text) && (
                  <span className="badge err" style={{ flexShrink: 0 }}>
                    evicted
                  </span>
                )}
              </button>
            ))
          ) : (
            <p className="muted small" style={{ padding: "var(--space-3)" }}>
              {evictedOnly
                ? "Nothing evicted by this profile."
                : "No targets on this screen."}
            </p>
          )}
        </div>
        <div className="stage-panes" id="stage-panes">
          {mode === "onion" ? (
            <div className="pane onion-pane-wrap">
              <div className="pane-head">
                <span className="pane-title">Baseline ↔ {label}</span>
                <span className="pane-dims" id="dims-baseline" />
                <button
                  type="button"
                  className="icon-btn small"
                  aria-label="Export composite as PNG"
                >
                  <Icon name="download" />
                </button>
              </div>
              <div
                className="pane-canvas onion-pane"
                id="onion-viewport"
                ref={onionWrap}
              >
                <div
                  className="onion-stack"
                  id="onion-stack"
                  style={{ clipPath: `inset(0 ${100 - onionPct}% 0 0)` }}
                >
                  <ScreenshotCanvas
                    dataset={dataset}
                    screen={screen}
                    profile="baseline"
                    targets={targets}
                    present={present}
                    missing={missing}
                    labels={labels}
                    selected={selected}
                    showBoxes={showBoxes}
                    showMissing={showMissing}
                    evictedOnly={evictedOnly}
                    zoom={zoom}
                    onSelect={setSelection}
                    id="baseline"
                    wrapperRef={onionWrap}
                  />
                  <ScreenshotCanvas
                    dataset={dataset}
                    screen={screen}
                    profile={profile}
                    targets={targets}
                    present={present}
                    missing={missing}
                    labels={labels}
                    selected={selected}
                    showBoxes={showBoxes}
                    showMissing={showMissing}
                    evictedOnly={evictedOnly}
                    zoom={zoom}
                    onSelect={setSelection}
                    id="profile"
                    wrapperRef={onionWrap}
                    className="onion-top"
                  />
                  <div
                    className="onion-divider"
                    id="onion-divider"
                    role="slider"
                    tabIndex={0}
                    aria-label="Reveal amount"
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={Math.round(onionPct)}
                    style={{ left: `${onionPct}%` }}
                    onPointerDown={(e) => {
                      dragging.current = true;
                      e.currentTarget.setPointerCapture(e.pointerId);
                    }}
                    onPointerMove={onDividerMove}
                    onPointerUp={() => {
                      dragging.current = false;
                    }}
                  />
                </div>
              </div>
              <p className="image-caption">
                Drag the divider, or use the arrow keys once it is focused.
              </p>
            </div>
          ) : (
            <>
              <div className="pane">
                <div className="pane-head">
                  <span className="pane-title">Baseline</span>
                  <span className="pane-dims" id="dims-baseline" />
                  <button
                    type="button"
                    className="icon-btn small"
                    aria-label="Export baseline pane as PNG"
                  >
                    <Icon name="download" />
                  </button>
                </div>
                <div
                  className="pane-canvas"
                  id="viewport-baseline"
                  ref={baseWrap}
                >
                  <ScreenshotCanvas
                    dataset={dataset}
                    screen={screen}
                    profile="baseline"
                    targets={targets}
                    present={present}
                    missing={missing}
                    labels={labels}
                    selected={selected}
                    showBoxes={showBoxes}
                    showMissing={showMissing}
                    evictedOnly={evictedOnly}
                    zoom={zoom}
                    onSelect={setSelection}
                    id="baseline"
                    wrapperRef={baseWrap}
                  />
                </div>
                <p className="image-caption">
                  {targets.length} groundable target
                  {targets.length === 1 ? "" : "s"}
                </p>
              </div>
              <div className="pane">
                <div className="pane-head">
                  <span className="pane-title">{label}</span>
                  <span className="pane-dims" id="dims-profile" />
                  <button
                    type="button"
                    className="icon-btn small"
                    aria-label="Export profile pane as PNG"
                  >
                    <Icon name="download" />
                  </button>
                </div>
                <div
                  className="pane-canvas"
                  id="viewport-profile"
                  ref={profileWrap}
                >
                  <ScreenshotCanvas
                    dataset={dataset}
                    screen={screen}
                    profile={profile}
                    targets={targets}
                    present={present}
                    missing={missing}
                    labels={labels}
                    selected={selected}
                    showBoxes={showBoxes}
                    showMissing={showMissing}
                    evictedOnly={evictedOnly}
                    zoom={zoom}
                    onSelect={setSelection}
                    id="profile"
                    wrapperRef={profileWrap}
                  />
                </div>
                <p className="image-caption">
                  {isBaseline
                    ? "Same capture as the left pane."
                    : `${targets.filter((t) => present.has(t.text)).length} of ${targets.length} baseline targets still present`}
                </p>
              </div>
            </>
          )}
        </div>
      </div>
      {!isBaseline && missing.length ? (
        <div className="note note-info" style={{ marginTop: "var(--space-4)" }}>
          <span className="note-label">Note</span>
          <b>
            {missing.length} target{missing.length === 1 ? "" : "s"} evicted by
            this profile.
          </b>{" "}
          A target that no longer renders cannot be grounded by any model, so it
          is scored as <code>off_screen</code> rather than as a miss.
        </div>
      ) : null}
      <div className="overlay-legend" style={{ marginTop: "var(--space-4)" }}>
        <span className="legend-item" style={{ color: "var(--viz-blue)" }}>
          <span className="legend-swatch" />
          Groundable target
        </span>
        <span className="legend-item" style={{ color: "var(--err)" }}>
          <span className="legend-swatch" />
          Missing from this profile
        </span>
        <span className="legend-item" style={{ color: "var(--warn)" }}>
          <span className="legend-swatch filled" />
          Selected
        </span>
      </div>
      <div className="pane-dims" aria-live="polite">
        Baseline {baseDims} · {label} {profileDims}
      </div>
      <div className="form-actions">
        <button
          type="button"
          className="secondary"
          onClick={() => {
            const canvas = baseWrap.current?.querySelector("canvas");
            if (canvas) exportCanvasAsPng(canvas, "baseline.png");
          }}
        >
          Export baseline
        </button>
        <button
          type="button"
          className="secondary"
          onClick={() => {
            const canvas = profileWrap.current?.querySelector("canvas");
            if (canvas) exportCanvasAsPng(canvas, "profile.png");
          }}
        >
          Export profile
        </button>
      </div>
    </div>
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
