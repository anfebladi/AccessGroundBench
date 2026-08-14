import { type RefObject } from "react";
import { Icon } from "../Icon";
import { ScreenshotCanvas } from "../ScreenshotCanvas";
import type { Label, Profile, Target } from "../types";

export function SideBySidePanes({
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
  selectTarget,
  label,
  isBaseline,
  baseWrap,
  profileWrap,
  exportPane,
  onBaseDimensions,
  onProfileDimensions,
  paneCanvasClass,
  viewportClass,
}: {
  dataset: string;
  screen: string;
  profile: Profile;
  targets: Target[];
  present: Set<string>;
  missing: Target[];
  labels: Label[];
  selected: string | null;
  showBoxes: boolean;
  showMissing: boolean;
  evictedOnly: boolean;
  selectTarget: (text: string) => void;
  label: string;
  isBaseline: boolean;
  baseWrap: RefObject<HTMLDivElement | null>;
  profileWrap: RefObject<HTMLDivElement | null>;
  exportPane: (wrap: RefObject<HTMLDivElement | null>, filename: string) => void;
  onBaseDimensions: (value: string) => void;
  onProfileDimensions: (value: string) => void;
  paneCanvasClass: string;
  viewportClass: string;
}) {
  return (
    <>
      <div className="flex min-w-0 flex-col gap-2">
        <div className="flex items-baseline justify-between gap-2 rounded-t-[var(--radius-md)] bg-[var(--panel-dark-2)] px-3 py-2 text-[var(--on-dark)]">
          <span className="text-sm font-semibold">Baseline</span>
          <span className="text-xs text-[var(--on-dark-muted)]" id="dims-baseline" />
          <button
            type="button"
            className="flex size-8 cursor-pointer items-center justify-center rounded-[var(--radius-md)] border border-[var(--on-dark-border)] bg-transparent text-[var(--on-dark-muted)] shadow-none transition-colors duration-150 hover:border-[var(--on-dark-muted)] hover:bg-[var(--panel-dark)] hover:text-[var(--on-dark)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--on-dark)] active:bg-[var(--panel-dark)]"
            aria-label="Export baseline pane as PNG"
            onClick={() => exportPane(baseWrap, "baseline.png")}
          >
            <Icon name="download" />
          </button>
        </div>
        <div className={viewportClass} id="viewport-baseline" ref={baseWrap}>
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
            onSelect={selectTarget}
            id="baseline"
            wrapperRef={baseWrap}
            className={paneCanvasClass}
            onDimensions={onBaseDimensions}
          />
        </div>
        <p className="mt-2 text-center text-xs text-[var(--muted)]">
          {targets.length} groundable target
          {targets.length === 1 ? "" : "s"}
        </p>
      </div>
      <div className="flex min-w-0 flex-col gap-2">
        <div className="flex items-baseline justify-between gap-2 rounded-t-[var(--radius-md)] bg-[var(--panel-dark-2)] px-3 py-2 text-[var(--on-dark)]">
          <span className="text-sm font-semibold">{label}</span>
          <span className="text-xs text-[var(--on-dark-muted)]" id="dims-profile" />
          <button
            type="button"
            className="flex size-8 cursor-pointer items-center justify-center rounded-[var(--radius-md)] border border-[var(--on-dark-border)] bg-transparent text-[var(--on-dark-muted)] shadow-none transition-colors duration-150 hover:border-[var(--on-dark-muted)] hover:bg-[var(--panel-dark)] hover:text-[var(--on-dark)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--on-dark)] active:bg-[var(--panel-dark)]"
            aria-label="Export profile pane as PNG"
            onClick={() => exportPane(profileWrap, "profile.png")}
          >
            <Icon name="download" />
          </button>
        </div>
        <div className={viewportClass} id="viewport-profile" ref={profileWrap}>
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
            onSelect={selectTarget}
            id="profile"
            wrapperRef={profileWrap}
            className={paneCanvasClass}
            onDimensions={onProfileDimensions}
          />
        </div>
        <p className="mt-2 text-center text-xs text-[var(--muted)]">
          {isBaseline
            ? "Same capture as the left pane."
            : `${targets.filter((t) => present.has(t.text)).length} of ${targets.length} baseline targets still present`}
        </p>
      </div>
    </>
  );
}
