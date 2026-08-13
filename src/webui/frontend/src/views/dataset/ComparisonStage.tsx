import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent as ReactPointerEvent } from "react";
import { exportCanvasAsPng } from "../../lib/export";
import { deleteView, listViews, saveView, type SavedView } from "../../lib/storage";
import { Icon } from "./Icon";
import { ScreenshotCanvas } from "./ScreenshotCanvas";
import { PROFILES, asText, ordered, type Label, type Mode, type Profile, type Target, type ViewConfig } from "./types";

export function ComparisonStage({
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
                className={`stage-target-item${
                  missing.some((item) => item.text === t.text)
                    ? " is-missing"
                    : ""
                }${selected === t.text ? " is-selected" : ""}`}
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
