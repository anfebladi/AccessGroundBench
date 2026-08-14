import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { cn } from "../../lib/utils";
export const TooltipProvider = TooltipPrimitive.Provider;
export const Tooltip = TooltipPrimitive.Root;
export const TooltipTrigger = TooltipPrimitive.Trigger;
export const TooltipContent = ({
  className,
  ...p
}: TooltipPrimitive.TooltipContentProps) => (
  <TooltipPrimitive.Portal>
    <TooltipPrimitive.Content
      sideOffset={4}
      className={cn(
        "z-50 rounded-[var(--radius-md)] bg-[var(--gray-900)] px-3 py-1.5 text-xs text-white",
        className,
      )}
      {...p}
    />
  </TooltipPrimitive.Portal>
);
