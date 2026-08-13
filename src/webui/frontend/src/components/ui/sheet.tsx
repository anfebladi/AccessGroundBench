import * as DialogPrimitive from "@radix-ui/react-dialog";
import { cn } from "../../lib/utils";

export const Sheet = DialogPrimitive.Root;
export const SheetTrigger = DialogPrimitive.Trigger;
export const SheetClose = DialogPrimitive.Close;
export const SheetTitle = DialogPrimitive.Title;
export const SheetDescription = DialogPrimitive.Description;

export const SheetContent = ({
  className,
  children,
  ...props
}: DialogPrimitive.DialogContentProps) => (
  <DialogPrimitive.Portal>
    <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-[rgba(9,9,11,0.5)]" />
    <DialogPrimitive.Content
      className={cn(
        "fixed inset-y-0 right-0 z-50 w-[min(90vw,24rem)] overflow-y-auto border-l border-[var(--border)] bg-[var(--surface)] p-[var(--space-5)] text-[var(--text)] shadow-[var(--elev-overlay)]",
        className,
      )}
      {...props}
    >
      {children}
    </DialogPrimitive.Content>
  </DialogPrimitive.Portal>
);
