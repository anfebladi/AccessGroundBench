import * as React from "react";
import { ChevronDownIcon } from "@radix-ui/react-icons";
import {
  Root as Collapsible,
  Trigger as CollapsibleTrigger,
  Content as CollapsibleContent,
} from "@radix-ui/react-collapsible";
import { cn } from "../../lib/utils";

export { Collapsible, CollapsibleTrigger, CollapsibleContent };

export const DisclosureTrigger = ({
  className,
  children,
  ...p
}: React.ComponentPropsWithoutRef<typeof CollapsibleTrigger>) => (
  <CollapsibleTrigger
    className={cn(
      "group flex items-center gap-1.5 text-sm font-medium text-[var(--text-2)] cursor-pointer transition-colors duration-[var(--dur-fast)] ease-[var(--ease)] hover:text-[var(--primary)]",
      className,
    )}
    {...p}
  >
    <ChevronDownIcon className="size-3 shrink-0 transition-transform duration-[var(--dur-fast)] ease-[var(--ease)] group-data-[state=open]:rotate-180" />
    {children}
  </CollapsibleTrigger>
);
