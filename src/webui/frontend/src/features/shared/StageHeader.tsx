import type { ReactNode } from "react";
import { routeGroupLabel, type Tab } from "../../app/navigation";

/**
 * The opening block of every workflow stage: phase eyebrow, title, and lead
 * description. The eyebrow comes from the sidebar's route groups so the phase
 * label is authored once.
 */
export function StageHeader({
  stage,
  title,
  children,
}: {
  stage: Tab;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="view-head mb-[var(--space-5)] max-w-[var(--prose-max)]">
      <p className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--primary)]">
        {routeGroupLabel(stage)}
      </p>
      <h2
        id={`head-${stage}`}
        className="text-[length:var(--text-display)] leading-[var(--lh-display)] tracking-[var(--ls-display)] max-[767px]:text-[1.375rem]"
      >
        {title}
      </h2>
      <p className="mt-2 font-[var(--font-ui)] text-[length:var(--text-lead)] leading-[var(--lh-lead)] text-[var(--text-2)]">
        {children}
      </p>
    </div>
  );
}
