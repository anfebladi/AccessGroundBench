import * as React from "react";
import { cn } from "../../lib/utils";
export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...p }, r) => (
  <textarea
    ref={r}
    className={cn(
      "min-h-20 w-full rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] px-[10px] py-[7px] text-sm text-[var(--text)] transition-[border-color,box-shadow] duration-[var(--dur-fast)] ease-[var(--ease)] placeholder:text-[var(--muted)] hover:not-disabled:border-[var(--text-2)] focus-visible:border-[var(--primary)] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-[var(--primary-soft)] disabled:cursor-not-allowed disabled:bg-[var(--surface-2)] disabled:text-[var(--muted)]",
      className,
    )}
    {...p}
  />
));
Textarea.displayName = "Textarea";
