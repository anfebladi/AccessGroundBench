import * as React from "react";
import { cn } from "../../lib/utils";
export const Badge = ({
  className,
  ...p
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn(
      "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium",
      className,
    )}
    {...p}
  />
);
