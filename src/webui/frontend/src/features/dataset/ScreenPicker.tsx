import { Input } from "../../components/ui/input";
import { Button } from "../../components/ui/button";

export function ScreenPicker({
  screens,
  selected,
  filter,
  onFilter,
  onSelect,
}: {
  screens: string[];
  selected: string | null;
  filter: string;
  onFilter: (value: string) => void;
  onSelect: (screen: string) => void;
}) {

  const visible = screens.filter((screen) =>
    screen.toLowerCase().includes(filter.trim().toLowerCase()),
  );
  return (
    <div className="flex w-60 min-w-0 shrink-0 flex-col gap-2 max-md:w-full">
      <Input
        id="screen-filter"
        type="search"
        placeholder="Filter screens"
        aria-label="Filter screens"
        value={filter}
        onChange={(event) => onFilter(event.target.value)}
      />
      <ul id="screen-list" className="m-0 max-h-[30rem] list-none overflow-y-auto p-0">
        {visible.length ? (
          visible.map((screen) => (
            <li
              data-screen={screen}
              className={`p-0 ${screen === selected ? "selected rounded-md bg-[var(--primary)] font-medium text-[var(--primary-fg)]" : ""}`}
              key={screen}
            >
              <Button
                type="button"
                className="w-full justify-start border-transparent bg-transparent px-2 py-1 text-left text-[var(--text)]"
                aria-label={screen}
                onClick={() => onSelect(screen)}
              >
                {screen}
              </Button>
            </li>
          ))
        ) : (
          <li className="cursor-default px-2 py-1 text-sm text-[var(--muted)]">
            No matching screens
          </li>
        )}
      </ul>
    </div>
  );
}
