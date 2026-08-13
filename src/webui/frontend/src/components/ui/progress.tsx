import * as ProgressPrimitive from "@radix-ui/react-progress";
import { cn } from "../../lib/utils";
export const Progress = ({
  className,
  value,
  ...p
}: ProgressPrimitive.ProgressProps) => (
  <ProgressPrimitive.Root
    className={cn(
      "relative h-2 w-full overflow-hidden rounded-full bg-[var(--surface-3)]",
      className,
    )}
    {...p}
  >
    <ProgressPrimitive.Indicator
      className="h-full w-full bg-[var(--primary)] transition-transform"
      style={{ transform: `translateX(-${100 - (value || 0)}%)` }}
    />
  </ProgressPrimitive.Root>
);
