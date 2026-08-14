import * as React from "react";
import { cn } from "../../lib/utils";
export const Card = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...p }, r) => (
  <div
    ref={r}
    className={cn(
      "mb-[var(--space-4)] rounded-[var(--radius-lg)] border border-[var(--border)]/60 bg-[var(--surface)] p-[var(--card-pad)] text-[var(--text)] shadow-[var(--elev-card)]",
      className,
    )}
    {...p}
  />
));
Card.displayName = "Card";
export const CardHeader = ({
  className,
  ...p
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("mb-4 flex flex-wrap items-start justify-between gap-4", className)} {...p} />
);
export const CardTitle = ({
  className,
  ...p
}: React.HTMLAttributes<HTMLHeadingElement>) => (
  <h3 className={cn("m-0 text-base font-semibold", className)} {...p} />
);
export const CardDescription = ({
  className,
  ...p
}: React.HTMLAttributes<HTMLParagraphElement>) => (
  <p className={cn("mt-1 max-w-[var(--prose-max)] text-sm text-[var(--muted)]", className)} {...p} />
);
export const CardContent = ({
  className,
  ...p
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("p-0", className)} {...p} />
);
export const CardFooter = ({
  className,
  ...p
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("mt-4 flex items-center", className)} {...p} />
);
