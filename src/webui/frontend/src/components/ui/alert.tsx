import { cn } from "../../lib/utils";
export const Alert = ({
  className,
  ...p
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    role="alert"
    className={cn(
      "relative w-full rounded-lg border border-[var(--border)] p-4 text-sm",
      className,
    )}
    {...p}
  />
);
export const AlertTitle = ({
  className,
  ...p
}: React.HTMLAttributes<HTMLHeadingElement>) => (
  <h5 className={cn("mb-1 font-medium", className)} {...p} />
);
export const AlertDescription = ({
  className,
  ...p
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("text-[var(--muted)]", className)} {...p} />
);
