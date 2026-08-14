import * as React from "react";
import {
  CrossCircledIcon,
  ExclamationTriangleIcon,
  InfoCircledIcon,
} from "@radix-ui/react-icons";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

const alertVariants = cva(
  "relative w-full border-l-[3px] py-0.5 pl-4 text-sm [&>*+*]:mt-1",
  {
    variants: {
      variant: {
        neutral: "border-l-[var(--border-strong)] text-[var(--muted)]",
        accent: "border-l-[var(--primary)] text-[var(--primary)]",
        warning: "border-l-[var(--warn)] text-[var(--warn)]",
        danger: "border-l-[var(--danger)] text-[var(--danger)]",
      },
    },
    defaultVariants: { variant: "neutral" },
  },
);

const variantIcons = {
  neutral: InfoCircledIcon,
  accent: InfoCircledIcon,
  warning: ExclamationTriangleIcon,
  danger: CrossCircledIcon,
} as const;

export interface AlertProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof alertVariants> {}

export const Alert = ({
  className,
  variant = "neutral",
  role,
  ...p
}: AlertProps) => (
  <div
    role={role ?? (variant === "danger" || variant === "warning" ? "alert" : "note")}
    className={cn(alertVariants({ variant }), className)}
    {...p}
  />
);

export const AlertIcon = ({
  variant,
  className,
}: {
  variant: NonNullable<AlertProps["variant"]>;
  className?: string;
}) => {
  const Icon = variantIcons[variant];
  return <Icon className={cn("size-4 shrink-0", className)} />;
};

export const AlertTitle = ({
  className,
  ...p
}: React.HTMLAttributes<HTMLHeadingElement>) => (
  <h5
    className={cn(
      "flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide",
      className,
    )}
    {...p}
  />
);

export const AlertDescription = ({
  className,
  ...p
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn("text-[var(--text-2)] normal-case tracking-normal", className)}
    {...p}
  />
);
