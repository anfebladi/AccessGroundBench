import { cn } from "../../lib/utils";
export const Command = ({
  className,
  ...p
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    role="dialog"
    className={cn(
      "flex h-full w-full flex-col overflow-hidden rounded-md bg-white text-[var(--text)]",
      className,
    )}
    {...p}
  />
);
export const CommandInput = ({
  className,
  ...p
}: React.InputHTMLAttributes<HTMLInputElement>) => (
  <input
    className={cn("h-10 w-full border-b px-3 text-sm outline-none", className)}
    {...p}
  />
);
export const CommandList = ({
  className,
  ...p
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn("max-h-72 overflow-y-auto overflow-x-hidden", className)}
    {...p}
  />
);
export const CommandEmpty = ({
  className,
  ...p
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("py-6 text-center text-sm", className)} {...p} />
);
export const CommandGroup = ({
  className,
  ...p
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("overflow-hidden p-1", className)} {...p} />
);
export const CommandItem = ({
  className,
  ...p
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    role="option"
    tabIndex={0}
    className={cn(
      "relative flex cursor-pointer items-center rounded-sm px-2 py-1.5 text-sm hover:bg-[var(--surface-2)]",
      className,
    )}
    {...p}
  />
);
