import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";
const variants = cva(
  "inline-flex items-center justify-center gap-2 rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--primary)] disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default:
          "bg-[var(--primary)] text-white hover:bg-[var(--primary-hover)]",
        secondary:
          "border border-[var(--border-strong)] bg-white text-[var(--text)] hover:bg-[var(--surface-2)]",
        outline:
          "border border-[var(--border)] bg-transparent hover:bg-[var(--surface-2)]",
        ghost: "hover:bg-[var(--surface-2)]",
        destructive:
          "bg-[var(--danger)] text-white hover:bg-[var(--danger-hover)]",
        link: "text-[var(--primary)] underline-offset-4 hover:underline",
      },
      size: {
        default: "min-h-8 px-3 py-1.5",
        sm: "min-h-7 px-2.5 text-xs",
        lg: "min-h-10 px-5",
        icon: "size-8",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);
export interface ButtonProps
  extends
    React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof variants> {
  asChild?: boolean;
}
export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(variants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";
