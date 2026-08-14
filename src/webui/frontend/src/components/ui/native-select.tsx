import * as React from "react";
import { cn } from "../../lib/utils";
export const NativeSelect = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement>
>(({ className, ...p }, r) => (
  <select
    ref={r}
    className={cn(
      "min-h-[var(--control-h)] w-full cursor-pointer appearance-none rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] bg-[url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath d='M1 1l5 5 5-5' fill='none' stroke='%2333404f' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E\")] bg-[position:right_10px_center] bg-no-repeat px-[10px] py-[7px] pr-8 text-sm text-[var(--text)] transition-[border-color,box-shadow] duration-[var(--dur-fast)] ease-[var(--ease)] hover:not-disabled:border-[var(--text-2)] focus-visible:border-[var(--primary)] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-[var(--primary-soft)] disabled:cursor-not-allowed disabled:bg-[var(--surface-2)] disabled:text-[var(--muted)] max-[767px]:min-h-[var(--tap)] [@media(pointer:coarse)]:min-h-[var(--tap)]",
      className,
    )}
    {...p}
  />
));
NativeSelect.displayName = "NativeSelect";
