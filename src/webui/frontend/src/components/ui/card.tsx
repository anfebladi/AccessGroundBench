import * as React from "react";
import { cn } from "../../lib/utils";
export const Card = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...p }, r) => (
  <div
    ref={r}
    className={cn(
      "rounded-lg border border-[var(--border)] bg-[var(--surface)] text-[var(--text)] shadow-sm",
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
  <div className={cn("flex flex-col space-y-1.5 p-4", className)} {...p} />
);
export const CardTitle = ({
  className,
  ...p
}: React.HTMLAttributes<HTMLHeadingElement>) => (
  <h3 className={cn("text-base font-semibold", className)} {...p} />
);
export const CardDescription = ({
  className,
  ...p
}: React.HTMLAttributes<HTMLParagraphElement>) => (
  <p className={cn("text-sm text-[var(--muted)]", className)} {...p} />
);
export const CardContent = ({
  className,
  ...p
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("p-4 pt-0", className)} {...p} />
);
export const CardFooter = ({
  className,
  ...p
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("flex items-center p-4 pt-0", className)} {...p} />
);
