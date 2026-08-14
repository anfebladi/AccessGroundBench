import { type RefObject } from "react";
import { Icon } from "../Icon";
import { ScreenshotCanvas } from "../ScreenshotCanvas";
import type { OnionDividerHandlers } from "./useOnionDivider";
import type { Label, Profile, Target } from "../types";

export function OnionPane({
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
  onionWrap,
  onionPct,
  dividerHandlers,
  exportOnionComposite,
  paneCanvasClass,
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
  onionWrap: RefObject<HTMLDivElement | null>;
  onionPct: number;
  dividerHandlers: OnionDividerHandlers;
  exportOnionComposite: () => void;
  paneCanvasClass: string;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <div className="flex items-baseline justify-between gap-2 rounded-t-[var(--radius-md)] bg-[var(--panel-dark-2)] px-3 py-2 text-[var(--on-dark)]">
        <span className="text-sm font-semibold">Baseline ↔ {label}</span>
        <span className="text-xs text-[var(--on-dark-muted)]" id="dims-baseline" />
        <button
          type="button"
          className="flex size-8 cursor-pointer items-center justify-center rounded-[var(--radius-md)] border border-[var(--on-dark-border)] bg-transparent text-[var(--on-dark-muted)] shadow-none transition-colors duration-150 hover:border-[var(--on-dark-muted)] hover:bg-[var(--panel-dark)] hover:text-[var(--on-dark)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--on-dark)] active:bg-[var(--panel-dark)]"
          aria-label="Export composite as PNG"
          onClick={exportOnionComposite}
        >
          <Icon name="download" />
        </button>
      </div>
      <div
        className="relative grid min-h-20 place-items-center overflow-auto rounded-[var(--radius-md)] bg-[var(--panel-dark)]"
        id="onion-viewport"
        ref={onionWrap}
      >
        <div className="relative inline-block max-w-full" id="onion-stack">
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
            wrapperRef={onionWrap}
            className={`block ${paneCanvasClass}`}
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
            onSelect={selectTarget}
            id="profile"
            wrapperRef={onionWrap}
            className="absolute inset-0 block h-full w-full object-contain"
            style={{ clipPath: `inset(0 ${100 - onionPct}% 0 0)` }}
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
            {...dividerHandlers}
          />
        </div>
      </div>
      <p className="mt-2 text-center text-xs text-[var(--muted)]">
        Drag the divider, or use the arrow keys once it is focused.
      </p>
    </div>
  );
}
