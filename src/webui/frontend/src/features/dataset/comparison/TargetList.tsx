import { Badge } from "../../../components/ui/badge";
import type { Target } from "../types";

export function TargetList({
  list,
  missing,
  selected,
  evictedOnly,
  selectTarget,
  clearSelection,
  moveSelection,
}: {
  list: Target[];
  missing: Target[];
  selected: string | null;
  evictedOnly: boolean;
  selectTarget: (text: string) => void;
  clearSelection: () => void;
  moveSelection: (direction: "next" | "prev") => void;
}) {
  return (
    <div
      className="min-w-0 max-h-[62vh] overflow-y-auto overflow-x-hidden border-r border-[var(--on-dark-border)] p-2 max-md:max-h-56"
      id="stage-target-list"
      role="listbox"
      aria-label="Groundable targets"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.preventDefault();
          clearSelection();
          return;
        }
        if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
        e.preventDefault();
        moveSelection(e.key === "ArrowDown" ? "next" : "prev");
      }}
    >
      {selected ? (
        <button
          type="button"
          className="mb-2 w-full cursor-pointer rounded border-2 border-white bg-white px-2 py-1 text-left text-xs font-semibold text-black transition-colors duration-[var(--dur-fast)] hover:bg-[var(--gray-100)]"
          onClick={clearSelection}
        >
          Clear selection
        </button>
      ) : null}
      {list.length ? (
        list.map((t) => (
          <button
            type="button"
            className={`flex w-full cursor-pointer items-center gap-2 rounded border border-transparent bg-transparent p-2 text-left text-sm text-[var(--on-dark-muted)] transition-colors duration-[var(--dur-fast)] ${
              selected === t.text
                ? "border-2 border-white bg-white text-black"
                : ""
            }`}
            aria-selected={selected === t.text}
            key={t.text}
            onClick={() => selectTarget(t.text)}
          >
            <span className={`size-2 shrink-0 rounded-full ${missing.some((m) => m.text === t.text) ? "bg-[var(--err)]" : "bg-[var(--ok)]"}`} aria-hidden="true" />
            <span className="min-w-0 flex-1 truncate" title={t.text}>
              {t.text}
            </span>
            {missing.some((m) => m.text === t.text) && (
              <Badge className="shrink-0 border-[var(--err)] text-[var(--err)]">
                evicted
              </Badge>
            )}
          </button>
        ))
      ) : (
        <p className="p-3 text-xs text-[var(--on-dark-muted)]">
          {evictedOnly
            ? "Nothing evicted by this profile."
            : "No targets on this screen."}
        </p>
      )}
    </div>
  );
}
