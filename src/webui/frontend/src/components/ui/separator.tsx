import * as SeparatorPrimitive from "@radix-ui/react-separator";
import { cn } from "../../lib/utils";
export const Separator = ({
  className,
  ...p
}: SeparatorPrimitive.SeparatorProps) => (
  <SeparatorPrimitive.Root
    className={cn(
      "shrink-0 bg-[var(--border)] data-[orientation=horizontal]:h-px data-[orientation=horizontal]:w-full data-[orientation=vertical]:h-full data-[orientation=vertical]:w-px",
      className,
    )}
    {...p}
  />
);
