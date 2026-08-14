import { useMemo, useRef, useState, type KeyboardEvent } from "react";
import { OnionPane } from "./OnionPane";
import { SideBySidePanes } from "./SideBySidePanes";
import { TargetList } from "./TargetList";
import { useOnionDivider } from "./useOnionDivider";
import { usePaneExport } from "./usePaneExport";
import { useTargetSelection } from "./useTargetSelection";
import { PROFILES, asText, ordered, type Label, type Profile, type Target, type Mode } from "../types";
import { Checkbox } from "../../../components/ui/checkbox";
import { SegmentedButton, SegmentedGroup } from "../../../components/ui/segmented";
import { Alert, AlertDescription, AlertIcon, AlertTitle } from "../../../components/ui/alert";

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
  const [evictedOnly, setEvictedOnly] = useState(false);
  const [baseDims, setBaseDims] = useState(""),
    [profileDims, setProfileDims] = useState("");
  const baseWrap = useRef<HTMLDivElement>(null);
  const profileWrap = useRef<HTMLDivElement>(null);
  const onionWrap = useRef<HTMLDivElement>(null);

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

  const { selected, selectTarget, clearSelection, moveSelection } =
    useTargetSelection(screen, list);
  const { onionPct, dividerHandlers } = useOnionDivider();
  const { exportPane, exportOnionComposite } = usePaneExport();

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (
      e.target instanceof HTMLElement &&
      (e.target.closest("#stage-target-list") ||
        e.target.closest("#onion-divider"))
    )
      return;
    if (
      !["j", "k", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(
        e.key,
      )
    )
      return;
    e.preventDefault();
    if (e.key.startsWith("Arrow")) {
      const dx = e.key === "ArrowLeft" ? -80 : e.key === "ArrowRight" ? 80 : 0;
      const dy = e.key === "ArrowUp" ? -80 : e.key === "ArrowDown" ? 80 : 0;
      [baseWrap.current, profileWrap.current, onionWrap.current].forEach((r) =>
        r?.scrollBy({ left: dx, top: dy }),
      );
      return;
    }
    moveSelection(e.key === "j" ? "next" : "prev");
  };

  /* Screenshots always render fit-to-pane. The canvas sets no explicit
     width/height, so the browser scales it down under these max-* constraints
     while keeping the capture's intrinsic aspect ratio. */
  const paneCanvasClass =
    "h-auto max-h-[62vh] w-auto max-w-full max-md:max-h-[55vh]";
  const viewportClass =
    "relative grid min-h-20 place-items-center overflow-auto rounded-[var(--radius-md)] bg-[var(--panel-dark)]";

  return (
    <div onKeyDown={onKeyDown}>
      <div className="flex items-center gap-3 p-3">
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
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={showBoxes}
              onCheckedChange={(v) => setShowBoxes(v === true)}
            />
            Target boxes
          </label>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={showMissing}
              onCheckedChange={(v) => setShowMissing(v === true)}
            />
            Missing targets
          </label>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={evictedOnly}
              onCheckedChange={(v) => setEvictedOnly(v === true)}
            />
            Evicted only
          </label>
        </div>
      </div>
      <div className="border-b border-[var(--border)] p-3 pt-0">
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
      </div>
      <div className="grid min-w-0 grid-cols-[13rem_minmax(0,1fr)] max-md:grid-cols-1">
        <TargetList
          list={list}
          missing={missing}
          selected={selected}
          evictedOnly={evictedOnly}
          selectTarget={selectTarget}
          clearSelection={clearSelection}
          moveSelection={moveSelection}
        />
        <div
          className={`min-w-0 p-3 ${
            mode === "side-by-side"
              ? "grid grid-cols-2 gap-3 max-md:grid-cols-1"
              : ""
          }`}
          id="stage-panes"
        >
          {mode === "onion" ? (
            <OnionPane
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
              selectTarget={selectTarget}
              label={label}
              onionWrap={onionWrap}
              onionPct={onionPct}
              dividerHandlers={dividerHandlers}
              exportOnionComposite={() => exportOnionComposite(onionWrap, onionPct)}
              paneCanvasClass={paneCanvasClass}
            />
          ) : (
            <SideBySidePanes
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
              selectTarget={selectTarget}
              label={label}
              isBaseline={isBaseline}
              baseWrap={baseWrap}
              profileWrap={profileWrap}
              exportPane={exportPane}
              onBaseDimensions={setBaseDims}
              onProfileDimensions={setProfileDims}
              paneCanvasClass={paneCanvasClass}
              viewportClass={viewportClass}
            />
          )}
        </div>
      </div>
      {!isBaseline && missing.length ? (
        <Alert
          variant="accent"
          className="mt-4 border-l-[var(--viz-blue)] text-[var(--viz-blue)]"
        >
          <AlertTitle>
            <AlertIcon variant="accent" />
            {missing.length} target{missing.length === 1 ? "" : "s"} evicted by
            this profile
          </AlertTitle>
          <AlertDescription>
            A target that no longer renders cannot be grounded by any model, so
            it is scored as <code>off_screen</code> rather than as a miss.
          </AlertDescription>
        </Alert>
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
    </div>
  );
}
