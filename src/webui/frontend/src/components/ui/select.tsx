import * as SelectPrimitive from "@radix-ui/react-select";
import { CheckIcon, ChevronDownIcon } from "@radix-ui/react-icons";
import * as React from "react";
import { cn } from "../../lib/utils";

export const Select = SelectPrimitive.Root;
export const SelectValue = SelectPrimitive.Value;

export const SelectTrigger = React.forwardRef<
  HTMLButtonElement,
  SelectPrimitive.SelectTriggerProps
>(({ className, children, ...p }, r) => (
  <SelectPrimitive.Trigger
    ref={r}
    className={cn(
      "flex min-h-[var(--control-h)] w-full cursor-pointer items-center justify-between gap-2 rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] px-[10px] py-[7px] text-sm text-[var(--text)] transition-[border-color,box-shadow] duration-[var(--dur-fast)] ease-[var(--ease)] hover:not-disabled:border-[var(--text-2)] focus-visible:border-[var(--primary)] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-[var(--primary-soft)] disabled:cursor-not-allowed disabled:bg-[var(--surface-2)] disabled:text-[var(--muted)] data-[placeholder]:text-[var(--muted)] max-[767px]:min-h-[var(--tap)] [@media(pointer:coarse)]:min-h-[var(--tap)]",
      className,
    )}
    {...p}
  >
    {children}
    <SelectPrimitive.Icon>
      <ChevronDownIcon className="size-3 shrink-0 text-[var(--primary)]" />
    </SelectPrimitive.Icon>
  </SelectPrimitive.Trigger>
));
SelectTrigger.displayName = "SelectTrigger";

export const SelectContent = React.forwardRef<
  HTMLDivElement,
  SelectPrimitive.SelectContentProps
>(({ className, children, ...p }, r) => (
  <SelectPrimitive.Portal>
    <SelectPrimitive.Content
      ref={r}
      position="popper"
      side="bottom"
      sideOffset={4}
      align="start"
      className={cn(
        "z-50 max-h-[min(24rem,var(--radix-select-content-available-height))] w-[var(--radix-select-trigger-width)] overflow-hidden rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] shadow-lg",
        className,
      )}
      {...p}
    >
      <SelectPrimitive.Viewport className="p-1">
        {children}
      </SelectPrimitive.Viewport>
    </SelectPrimitive.Content>
  </SelectPrimitive.Portal>
));
SelectContent.displayName = "SelectContent";

export const SelectItem = React.forwardRef<
  HTMLDivElement,
  SelectPrimitive.SelectItemProps
>(({ className, children, ...p }, r) => (
  <SelectPrimitive.Item
    ref={r}
    className={cn(
      "relative flex min-h-[var(--tap)] cursor-pointer select-none items-center rounded-[var(--radius-sm)] py-[6px] pl-7 pr-2 text-sm text-[var(--text)] outline-none data-[disabled]:cursor-not-allowed data-[disabled]:text-[var(--muted)] data-[highlighted]:bg-[var(--primary)] data-[highlighted]:text-white",
      className,
    )}
    {...p}
  >
    <SelectPrimitive.ItemIndicator className="absolute left-2 flex size-3 items-center justify-center">
      <CheckIcon className="size-3" />
    </SelectPrimitive.ItemIndicator>
    <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
  </SelectPrimitive.Item>
));
SelectItem.displayName = "SelectItem";
