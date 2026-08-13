import { cn } from "../../lib/utils";
export const Table = ({
  className,
  ...p
}: React.HTMLAttributes<HTMLTableElement>) => (
  <div className="relative w-full overflow-auto">
    <table className={cn("w-full caption-bottom text-sm", className)} {...p} />
  </div>
);
export const TableHeader = ({
  className,
  ...p
}: React.HTMLAttributes<HTMLTableSectionElement>) => (
  <thead className={cn("[&_tr]:border-b", className)} {...p} />
);
export const TableBody = ({
  className,
  ...p
}: React.HTMLAttributes<HTMLTableSectionElement>) => (
  <tbody className={cn("[&_tr:last-child]:border-0", className)} {...p} />
);
export const TableRow = ({
  className,
  ...p
}: React.HTMLAttributes<HTMLTableRowElement>) => (
  <tr
    className={cn(
      "border-b transition-colors hover:bg-[var(--surface-2)]",
      className,
    )}
    {...p}
  />
);
export const TableHead = ({
  className,
  ...p
}: React.ThHTMLAttributes<HTMLTableCellElement>) => (
  <th
    className={cn(
      "h-9 px-3 text-left align-middle text-xs font-medium text-[var(--muted)]",
      className,
    )}
    {...p}
  />
);
export const TableCell = ({
  className,
  ...p
}: React.TdHTMLAttributes<HTMLTableCellElement>) => (
  <td className={cn("p-3 align-middle", className)} {...p} />
);
