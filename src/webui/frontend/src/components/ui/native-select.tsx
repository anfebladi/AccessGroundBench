import * as React from "react";
import { cn } from "../../lib/utils";
export const NativeSelect = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement>
>(({ className, ...p }, r) => (
  <select
    ref={r}
    className={cn(
      "h-8 w-full rounded-md border border-[var(--border-strong)] bg-white px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--primary)]",
      className,
    )}
    {...p}
  />
));
NativeSelect.displayName = "NativeSelect";
