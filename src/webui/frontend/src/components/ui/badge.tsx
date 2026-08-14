import * as React from "react";
import { cn } from "../../lib/utils";
export const Badge = ({
  className,
  ...p
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn(
      "inline-flex items-center gap-1.5 rounded-full bg-[color-mix(in_srgb,currentColor_12%,transparent)] px-[9px] py-[3px] text-xs font-medium leading-none before:size-1.5 before:shrink-0 before:rounded-full before:bg-current before:content-['']",
      className,
    )}
    {...p}
  />
);
