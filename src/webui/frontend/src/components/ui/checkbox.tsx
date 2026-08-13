import * as CheckboxPrimitive from "@radix-ui/react-checkbox";
import { CheckIcon } from "@radix-ui/react-icons";
import { cn } from "../../lib/utils";
export const Checkbox = ({
  className,
  ...p
}: CheckboxPrimitive.CheckboxProps) => (
  <CheckboxPrimitive.Root
    className={cn(
      "peer !size-4 !min-h-0 !p-0 !shadow-none shrink-0 rounded-sm border border-[var(--border-strong)] bg-[var(--surface)] text-transparent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--primary)] data-[state=unchecked]:bg-[var(--surface)] data-[state=unchecked]:text-transparent data-[state=checked]:border-[var(--primary)] data-[state=checked]:bg-[var(--primary)] data-[state=checked]:text-white hover:data-[state=unchecked]:!bg-[var(--surface)] hover:data-[state=unchecked]:!border-[var(--border-strong)] active:data-[state=unchecked]:!bg-[var(--surface)] hover:data-[state=checked]:!bg-[var(--primary)]",
      className,
    )}
    {...p}
  >
    <CheckboxPrimitive.Indicator>
      <CheckIcon className="size-3" />
    </CheckboxPrimitive.Indicator>
  </CheckboxPrimitive.Root>
);
