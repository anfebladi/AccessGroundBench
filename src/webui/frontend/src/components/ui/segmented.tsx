import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

/* The segmented control the design system's state table has always described
   (docs/ui-design-system.md §5): 6% ink wash on hover, an `aria-pressed` chip
   for the active option. Built on cva rather than a Radix toggle group so it
   adds no dependency -- the UI resolves everything from the lockfile. */
const groupVariants = cva(
  "inline-flex flex-wrap items-center gap-1 rounded-[var(--radius-full)] border border-[var(--border)] bg-[var(--surface-2)] p-1",
);

export const SegmentedGroup = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div ref={ref} role="group" className={cn(groupVariants({ className }))} {...props} />
));
SegmentedGroup.displayName = "SegmentedGroup";

const buttonVariants = cva(
  "inline-flex min-h-[var(--control-h)] items-center justify-center gap-2 whitespace-nowrap rounded-[var(--radius-full)] border px-3 py-[6px] text-sm leading-none transition-[background-color,border-color,box-shadow] duration-[var(--dur-fast)] ease-[var(--ease)] cursor-pointer disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-45 max-[767px]:min-h-[var(--tap)] [@media(pointer:coarse)]:min-h-[var(--tap)]",
  {
    variants: {
      pressed: {
        /* --primary-fg on --primary measures 7.15:1, so the active chip clears
           AA on its own -- and the state never rides on colour alone anyway,
           since aria-pressed carries it to assistive tech. */
        true: "border-[var(--primary)] bg-[var(--primary)] font-medium text-[var(--primary-fg)] shadow-[var(--elev-card)] hover:bg-[var(--primary-hover)] hover:border-[var(--primary-hover)]",
        false:
          "border-transparent bg-transparent font-normal text-[var(--text-2)] hover:bg-[var(--primary-soft)]",
      },
      size: {
        default: "",
        sm: "min-h-[var(--control-h-sm)] px-2.5 py-[5px] text-xs max-[767px]:min-h-[var(--tap)] [@media(pointer:coarse)]:min-h-[var(--tap)]",
      },
    },
    defaultVariants: { pressed: false, size: "default" },
  },
);

export interface SegmentedButtonProps
  extends
    Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "aria-pressed" | "type">,
    Omit<VariantProps<typeof buttonVariants>, "pressed"> {
  pressed: boolean;
}

export const SegmentedButton = React.forwardRef<
  HTMLButtonElement,
  SegmentedButtonProps
>(({ className, pressed, size, ...props }, ref) => (
  <button
    ref={ref}
    type="button"
    aria-pressed={pressed}
    className={cn(buttonVariants({ pressed, size, className }))}
    {...props}
  />
));
SegmentedButton.displayName = "SegmentedButton";
