import * as React from "react";
import { cn } from "../../lib/utils";
export const Input = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ className, ...p }, r) => (
  <input
    ref={r}
    className={cn(
      "flex h-8 w-full rounded-md border border-[var(--border-strong)] bg-white px-3 py-1 text-sm text-[var(--text)] shadow-sm placeholder:text-[var(--muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--primary)] disabled:cursor-not-allowed disabled:opacity-50",
      className,
    )}
    {...p}
  />
));
Input.displayName = "Input";
