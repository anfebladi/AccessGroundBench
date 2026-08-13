import { cn } from "../../lib/utils";
export const Skeleton = ({
  className,
  ...p
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn("skeleton rounded-[var(--radius-md)] bg-[linear-gradient(90deg,var(--surface-2)_25%,var(--surface-3)_37%,var(--surface-2)_63%)] bg-[length:400%_100%] animate-pulse [animation:shimmer_1.4s_ease_infinite]", className)}
    {...p}
  />
);
