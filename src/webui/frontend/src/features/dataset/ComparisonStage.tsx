import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent as ReactPointerEvent } from "react";
import { exportCanvasAsPng } from "../../lib/export";
import { deleteView, listViews, saveView, type SavedView } from "../../lib/storage";
import { Icon } from "./Icon";
import { ScreenshotCanvas } from "./ScreenshotCanvas";
import { PROFILES, asText, ordered, type Label, type Mode, type Profile, type Target, type ViewConfig } from "./types";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { SegmentedButton, SegmentedGroup } from "../../components/ui/segmented";

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
  const selectTarget = (text: string) => setSelected(text);
  const clearSelection = () => setSelected(null);
  useEffect(() => {
    setSelected(null);
  }, [screen]);
  useEffect(() => {
    if (selected && !list.some((target) => target.text === selected)) {
      setSelected(null);
    }
  }, [list, selected]);
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
    if (next) selectTarget(next.text);
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
      <SegmentedGroup
        id="profile-picker"
        aria-label="Accessibility profile"
      >
        {PROFILES.map(([id, text]) => (
          <SegmentedButton
            key={id}
            pressed={id === profile}
            onClick={() => setProfile(id)}
          >
            {text}
          </SegmentedButton>
        ))}
      </SegmentedGroup>
      <div className="flex items-center justify-between gap-3 border-b border-[var(--on-dark-border)] p-3">
        <SegmentedGroup id="stage-mode-picker" aria-label="Comparison mode">
          <SegmentedButton
            pressed={mode === "side-by-side"}
            onClick={() => setMode("side-by-side")}
          >
            Side by side
          </SegmentedButton>
          <SegmentedButton
            pressed={mode === "onion"}
            onClick={() => setMode("onion")}
          >
            Onion-skin
          </SegmentedButton>
        </SegmentedGroup>
        <SegmentedGroup id="stage-zoom" aria-label="Zoom">
          {/* − and + are repeatable actions, not toggles: giving them
              aria-pressed would report a state they never hold. */}
          <Button
            variant="ghost"
            size="icon"
            onClick={() => changeZoom("out")}
            aria-label="Zoom out"
          >
            −
          </Button>
          <SegmentedButton
            pressed={zoom === "fit"}
            onClick={() => changeZoom("fit")}
          >
            Fit
          </SegmentedButton>
          <SegmentedButton
            pressed={zoom === 1}
            onClick={() => changeZoom("1:1")}
          >
            1:1
          </SegmentedButton>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => changeZoom("in")}
            aria-label="Zoom in"
          >
            +
          </Button>
        </SegmentedGroup>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={evictedOnly}
            onChange={(e) => setEvictedOnly(e.target.checked)}
          />{" "}
          Evicted only
        </label>
      </div>
      <div className="mt-2 flex items-center justify-between gap-3 border-b border-[var(--on-dark-border)] p-3">
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
          className="shadow-none"
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
          className="shadow-none"
          id="stage-view-save"
          title="Save current view"
          aria-label="Save current view"
          onClick={saveCurrent}
        >
          <Icon name="bookmark" />
        </button>
      </div>
      <div className="grid min-w-0 grid-cols-[13rem_minmax(0,1fr)] max-md:grid-cols-1">
        <div
          className="min-w-0 overflow-y-auto border-r border-[var(--on-dark-border)] p-2 max-md:max-h-56"
          id="stage-target-list"
          role="listbox"
          aria-label="Groundable targets"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.preventDefault();
              clearSelection();
              return;
            }
            if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
            e.preventDefault();
            const i = list.findIndex((x) => x.text === selected);
            const n =
              e.key === "ArrowDown"
                ? Math.min(list.length - 1, i + 1)
                : Math.max(0, i <= 0 ? 0 : i - 1);
            if (list[n]) selectTarget(list[n].text);
          }}
        >
          {selected ? (
            <button
              type="button"
              className="mb-2 w-full rounded border-2 border-white bg-white px-2 py-1 text-left text-xs font-semibold text-black"
              onClick={clearSelection}
            >
              Clear selection
            </button>
          ) : null}
          {list.length ? (
            list.map((t) => (
              <button
                type="button"
                className={`flex w-full items-center gap-2 rounded border border-transparent bg-transparent p-2 text-left text-sm text-[var(--on-dark-muted)] ${
                  selected === t.text
                    ? "border-2 border-white bg-white text-black"
                    : ""
                }`}
                aria-selected={selected === t.text}
                key={t.text}
                onClick={() => selectTarget(t.text)}
              >
                <span className={`size-2 shrink-0 rounded-full ${missing.some((m) => m.text === t.text) ? "bg-[var(--err)]" : "bg-[var(--ok)]"}`} aria-hidden="true" />
                <span>{t.text}</span>
                {missing.some((m) => m.text === t.text) && (
                  <Badge className="shrink-0 border-[var(--err)] text-[var(--err)]">
                    evicted
                  </Badge>
                )}
              </button>
            ))
          ) : (
            <p className="p-3 text-xs text-[var(--on-dark-muted)]">
              {evictedOnly
                ? "Nothing evicted by this profile."
                : "No targets on this screen."}
            </p>
          )}
        </div>
      <div
        className={`min-w-0 p-3 ${
          mode === "side-by-side"
            ? "grid grid-cols-2 gap-3 max-md:grid-cols-1"
            : ""
        }`}
        id="stage-panes"
      >
          {mode === "onion" ? (
            <div className="flex min-w-0 flex-col gap-2">
              <div className="flex items-baseline justify-between gap-2 rounded-t-md bg-[var(--panel-dark-2)] px-3 py-2 text-[var(--on-dark)]">
                <span className="text-sm font-semibold">Baseline ↔ {label}</span>
                <span className="text-xs text-[var(--on-dark-muted)]" id="dims-baseline" />
                <button
                  type="button"
                  className="size-8 border border-[var(--on-dark-border)] bg-transparent text-[var(--on-dark-muted)] shadow-none"
                  aria-label="Export composite as PNG"
                >
                  <Icon name="download" />
                </button>
              </div>
              <div
                className="relative grid min-h-20 place-items-center overflow-auto rounded-md bg-[var(--panel-dark)]"
                id="onion-viewport"
                ref={onionWrap}
              >
                <div
                  className="relative min-h-20 max-w-full"
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
                    onSelect={selectTarget}
                    id="baseline"
                    wrapperRef={onionWrap}
                    className="absolute inset-0 block h-full w-full"
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
                    onSelect={selectTarget}
                    id="profile"
                    wrapperRef={onionWrap}
                    className="absolute inset-0 block h-full w-full [clip-path:inset(0_50%_0_0)]"
                  />
                  <div
                    className="absolute inset-y-0 left-1/2 w-1 -translate-x-1/2 cursor-ew-resize bg-[var(--on-dark)]"
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
              <p className="mt-2 text-center text-xs text-[var(--muted)]">
                Drag the divider, or use the arrow keys once it is focused.
              </p>
            </div>
          ) : (
            <>
              <div className="flex min-w-0 flex-col gap-2">
                <div className="flex items-baseline justify-between gap-2 rounded-t-md bg-[var(--panel-dark-2)] px-3 py-2 text-[var(--on-dark)]">
                  <span className="text-sm font-semibold">Baseline</span>
                  <span className="text-xs text-[var(--on-dark-muted)]" id="dims-baseline" />
                  <button
                    type="button"
                    className="size-8 border border-[var(--on-dark-border)] bg-transparent text-[var(--on-dark-muted)] shadow-none"
                    aria-label="Export baseline pane as PNG"
                  >
                    <Icon name="download" />
                  </button>
                </div>
                <div
                  className="relative grid min-h-20 place-items-center overflow-auto rounded-md bg-[var(--panel-dark)]"
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
                    onSelect={selectTarget}
                    id="baseline"
                    wrapperRef={baseWrap}
                    className="h-auto max-h-[62vh] w-auto max-w-full max-md:max-h-[55vh]"
                  />
                </div>
                <p className="mt-2 text-center text-xs text-[var(--muted)]">
                  {targets.length} groundable target
                  {targets.length === 1 ? "" : "s"}
                </p>
              </div>
              <div className="flex min-w-0 flex-col gap-2">
                <div className="flex items-baseline justify-between gap-2 rounded-t-md bg-[var(--panel-dark-2)] px-3 py-2 text-[var(--on-dark)]">
                  <span className="text-sm font-semibold">{label}</span>
                  <span className="text-xs text-[var(--on-dark-muted)]" id="dims-profile" />
                  <button
                    type="button"
                    className="size-8 border border-[var(--on-dark-border)] bg-transparent text-[var(--on-dark-muted)] shadow-none"
                    aria-label="Export profile pane as PNG"
                  >
                    <Icon name="download" />
                  </button>
                </div>
                <div
                  className="relative grid min-h-20 place-items-center overflow-auto rounded-md bg-[var(--panel-dark)]"
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
                    onSelect={selectTarget}
                    id="profile"
                    wrapperRef={profileWrap}
                    className="h-auto max-h-[62vh] w-auto max-w-full max-md:max-h-[55vh]"
                  />
                </div>
                <p className="mt-2 text-center text-xs text-[var(--muted)]">
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
        <div className="mt-4 rounded-md border border-[var(--viz-blue)]/40 bg-[var(--viz-blue)]/10 p-3 text-sm">
          <span className="font-semibold">Note</span>
          <b>
            {missing.length} target{missing.length === 1 ? "" : "s"} evicted by
            this profile.
          </b>{" "}
          A target that no longer renders cannot be grounded by any model, so it
          is scored as <code>off_screen</code> rather than as a miss.
        </div>
      ) : null}
      <div className="mt-4 flex flex-wrap gap-3 text-xs">
        <span className="flex items-center gap-1 text-[var(--viz-blue)]">
          <span className="size-2 rounded-full border border-current" />
          Groundable target
        </span>
        <span className="flex items-center gap-1 text-[var(--err)]">
          <span className="size-2 rounded-full border border-current" />
          Missing from this profile
        </span>
        <span className="flex items-center gap-1 text-[var(--warn)]">
          <span className="size-2 rounded-full bg-current" />
          Selected
        </span>
      </div>
      <div className="text-xs text-[var(--on-dark-muted)]" aria-live="polite">
        Baseline {baseDims} · {label} {profileDims}
      </div>
      <div className="sr-only" aria-live="polite" role="status">
        {selected ? `Selected target: ${selected}` : "No target selected"}
      </div>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm hover:bg-[var(--surface-2)]"
          onClick={() => {
            const canvas = baseWrap.current?.querySelector("canvas");
            if (canvas) exportCanvasAsPng(canvas, "baseline.png");
          }}
        >
          Export baseline
        </button>
        <button
          type="button"
          className="rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm hover:bg-[var(--surface-2)]"
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
