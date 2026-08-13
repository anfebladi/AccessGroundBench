import { cn } from "../../lib/utils";
export const Skeleton = ({
  className,
  ...p
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn("animate-pulse rounded-md bg-[var(--surface-3)]", className)}
    {...p}
  />
);
