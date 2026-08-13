import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";
const variants = cva(
  "inline-flex min-h-[var(--control-h)] items-center justify-center gap-2 whitespace-nowrap rounded-[var(--radius-md)] border px-[14px] py-[7px] text-sm font-medium leading-none transition-[background-color,border-color,box-shadow] duration-[var(--dur-fast)] ease-[var(--ease)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--primary)] disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-45 disabled:shadow-none max-[767px]:min-h-[var(--tap)] [@media(pointer:coarse)]:min-h-[var(--tap)]",
  {
    variants: {
      variant: {
        default:
          "border-[var(--primary)] bg-[var(--primary)] text-[var(--primary-fg)] shadow-none hover:border-[var(--primary-hover)] hover:bg-[var(--primary-hover)] hover:shadow-[var(--elev-card)] active:border-[var(--primary-active)] active:bg-[var(--primary-active)] active:shadow-none",
        secondary:
          "border-[var(--border-strong)] bg-[var(--surface)] text-[var(--text)] hover:border-[var(--text-2)] hover:bg-[var(--surface-2)] active:bg-[var(--surface-3)]",
        outline:
          "border-[var(--border-strong)] bg-transparent text-[var(--text)] hover:bg-[var(--surface-2)]",
        ghost: "border-transparent bg-transparent text-[var(--primary)] shadow-none hover:border-transparent hover:bg-[var(--primary-soft)] hover:shadow-none",
        destructive:
          "border-[var(--danger)] bg-[var(--danger)] text-white hover:border-[var(--danger-hover)] hover:bg-[var(--danger-hover)] active:border-[var(--danger-active)] active:bg-[var(--danger-active)]",
        link: "text-[var(--primary)] underline-offset-4 hover:underline",
      },
      size: {
        default: "",
        sm: "min-h-[var(--control-h-sm)] px-2.5 py-[5px] text-xs max-[767px]:min-h-[var(--tap)] [@media(pointer:coarse)]:min-h-[var(--tap)]",
        lg: "min-h-10 px-5",
        icon: "size-[var(--control-h)] min-w-[var(--control-h)] px-[6px] py-[6px] max-[767px]:size-[var(--tap)] max-[767px]:min-w-[var(--tap)] [@media(pointer:coarse)]:size-[var(--tap)] [@media(pointer:coarse)]:min-w-[var(--tap)]",
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
