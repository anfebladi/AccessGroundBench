import { cn } from "../../lib/utils";

/* The ring is decorative unless given a label: inside LoadingState the
   accessible name sits on the wrapper, but small inline slots (top bar,
   rail chips) name the ring itself. Under prefers-reduced-motion the
   rotation collapses, so the name -- not the motion -- is the signal. */
export const Spinner = ({
  label,
  className,
  ...p
}: React.HTMLAttributes<HTMLSpanElement> & { label?: string }) => (
  <span
    role={label ? "status" : undefined}
    aria-label={label}
    aria-hidden={label ? undefined : true}
    className={cn(
      "inline-block size-6 shrink-0 animate-spin rounded-full border-2 border-[var(--border)] border-t-[var(--primary)]",
      className,
    )}
    {...p}
  />
);

export const LoadingState = ({
  label = "Loading…",
  className,
  ...p
}: React.HTMLAttributes<HTMLDivElement> & { label?: string }) => (
  <div
    role="status"
    aria-busy="true"
    aria-label={label}
    className={cn("flex flex-col items-center justify-center gap-3 p-6", className)}
    {...p}
  >
    <Spinner />
    <p className="text-sm text-[var(--muted)]">{label}</p>
  </div>
);
