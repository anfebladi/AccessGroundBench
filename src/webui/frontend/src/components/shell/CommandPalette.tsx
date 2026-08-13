import { useEffect, useMemo, useState } from "react";
import type { PaletteItem } from "../../app/navigation";
import {
  Command,
  CommandEmpty,
  CommandInput,
  CommandItem,
  CommandList,
} from "../ui/command";

export function CommandPalette({
  items,
  open,
  onSelect,
  onClose,
}: {
  items: PaletteItem[];
  open: boolean;
  onSelect: (x: PaletteItem) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items
      .filter((x) => !q || x.label.toLowerCase().includes(q))
      .sort((a, b) =>
        q
          ? Number(!a.label.toLowerCase().startsWith(q)) -
            Number(!b.label.toLowerCase().startsWith(q))
          : 0,
      );
  }, [items, query]);

  useEffect(() => setActive(0), [query, open]);

  useEffect(() => {
    if (open) document.getElementById("palette-input")?.focus();
  }, [open]);

  const keyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((v) => Math.min(Math.max(0, filtered.length - 1), v + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((v) => Math.max(0, v - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (filtered[active]) onSelect(filtered[active]);
    } else if (e.key === "Escape") onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-start justify-center bg-[rgba(9,9,11,0.5)] px-4 pt-[min(14vh,var(--space-8))]"
      id="palette-backdrop"
      hidden={!open}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <Command
        className="w-[min(560px,100%)] overflow-hidden rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] shadow-[var(--elev-overlay)]"
        aria-modal="true"
        aria-label="Command palette"
      >
        <div className="border-b border-[var(--border)]">
          <CommandInput
            autoComplete="off"
            type="text"
            id="palette-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={keyDown}
            className="w-full rounded-none border-0 shadow-none"
            role="combobox"
            aria-expanded="true"
            aria-controls="palette-list"
            aria-autocomplete="list"
            aria-activedescendant={
              filtered.length ? `palette-opt-${active}` : undefined
            }
            placeholder="Jump to a view, screen, or model…"
          />
        </div>
        <CommandList id="palette-list" role="listbox" aria-label="Results">
          {filtered.length ? (
            filtered.map((item, i) => (
              <CommandItem
                id={`palette-opt-${i}`}
                className={`relative flex cursor-pointer items-center justify-between gap-3 rounded-md p-3 text-sm ${i === active ? "bg-[var(--primary-soft)] text-[var(--primary)]" : "hover:bg-[var(--surface-2)]"}`}
                aria-selected={i === active}
                key={`${item.hint}-${item.label}`}
                onClick={() => onSelect(item)}
              >
                <span className="overflow-hidden text-ellipsis whitespace-nowrap">{item.label}</span>
                <span className="shrink-0 text-xs text-[var(--muted)]">{item.hint}</span>
              </CommandItem>
            ))
          ) : (
            <CommandEmpty className="py-6 text-center text-sm text-[var(--muted)]">No matches</CommandEmpty>
          )}
        </CommandList>
        <div className="flex flex-wrap gap-3 border-t border-[var(--border)] p-3 text-xs text-[var(--muted)]">
          <span>
            <kbd>↑</kbd>
            <kbd>↓</kbd> navigate
          </span>
          <span>
            <kbd>Enter</kbd> select
          </span>
          <span>
            <kbd>Esc</kbd> close
          </span>
          <span>
            <kbd>1</kbd>–<kbd>7</kbd> jump to a view
          </span>
        </div>
      </Command>
    </div>
  );
}
