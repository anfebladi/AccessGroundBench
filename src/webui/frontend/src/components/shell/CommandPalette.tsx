import { useEffect, useMemo, useState } from "react";
import type { PaletteItem } from "../../app/navigation";
import styles from "./Shell.module.css";

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
      className={styles.paletteBackdrop}
      id="palette-backdrop"
      hidden={!open}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className={styles.palette}
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
      >
        <div className="palette-input-row">
          <input
            autoComplete="off"
            type="text"
            id="palette-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={keyDown}
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
        <ul id="palette-list" role="listbox" aria-label="Results">
          {filtered.length ? (
            filtered.map((item, i) => (
              <li
                role="option"
                id={`palette-opt-${i}`}
                className={i === active ? "is-active" : ""}
                aria-selected={i === active}
                key={`${item.hint}-${item.label}`}
                onClick={() => onSelect(item)}
              >
                <span className="palette-item-label">{item.label}</span>
                <span className="palette-item-hint">{item.hint}</span>
              </li>
            ))
          ) : (
            <li className="palette-empty muted small">No matches</li>
          )}
        </ul>
        <div className="palette-foot">
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
      </div>
    </div>
  );
}
