import * as React from "react";
import { cn } from "../../lib/utils";
export const Input = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ className, ...p }, r) => (
  <input
    ref={r}
    className={cn(
      "min-h-[var(--control-h)] w-full rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] px-[10px] py-[7px] text-sm text-[var(--text)] placeholder:text-[var(--muted)] transition-[border-color,box-shadow] duration-[var(--dur-fast)] ease-[var(--ease)] hover:not-disabled:border-[var(--text-2)] focus-visible:border-[var(--primary)] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-[var(--primary-soft)] disabled:cursor-not-allowed disabled:bg-[var(--surface-2)] disabled:text-[var(--muted)] max-[767px]:min-h-[var(--tap)] [@media(pointer:coarse)]:min-h-[var(--tap)]",
      className,
    )}
    {...p}
  />
));
Input.displayName = "Input";
