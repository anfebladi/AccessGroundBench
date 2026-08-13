import * as React from "react";
import { cn } from "../../lib/utils";
export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...p }, r) => (
  <textarea
    ref={r}
    className={cn(
      "min-h-20 w-full rounded-md border border-[var(--border-strong)] bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--primary)]",
      className,
    )}
    {...p}
  />
));
Textarea.displayName = "Textarea";
