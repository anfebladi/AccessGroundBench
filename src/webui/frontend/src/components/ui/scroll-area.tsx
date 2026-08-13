import * as ScrollAreaPrimitive from "@radix-ui/react-scroll-area";
import { cn } from "../../lib/utils";
export const ScrollArea = ({
  className,
  ...p
}: ScrollAreaPrimitive.ScrollAreaProps) => (
  <ScrollAreaPrimitive.Root
    className={cn("relative overflow-hidden", className)}
    {...p}
  >
    <ScrollAreaPrimitive.Viewport className="size-full rounded-[inherit]">
      <>{p.children}</>
    </ScrollAreaPrimitive.Viewport>
    <ScrollAreaPrimitive.Scrollbar
      orientation="vertical"
      className="flex w-2.5 touch-none select-none p-0.5"
    >
      <ScrollAreaPrimitive.Thumb className="relative flex-1 rounded-full bg-[var(--border-strong)]" />
    </ScrollAreaPrimitive.Scrollbar>
  </ScrollAreaPrimitive.Root>
);
