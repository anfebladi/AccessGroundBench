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
      <ul
        id="screen-list"
        className="m-0 flex max-h-[30rem] flex-col gap-1 list-none overflow-y-auto rounded-[var(--radius-lg)] bg-[var(--surface-warm)] p-[var(--space-2)] shadow-[var(--elev-card)]"
      >
        {visible.length ? (
          visible.map((screen) => (
            <li
              data-screen={screen}
              className={screen === selected ? "selected p-0" : "p-0"}
              key={screen}
            >
              <Button
                type="button"
                variant="ghost"
                className={`w-full justify-start rounded-[var(--radius-full)] px-3 py-1.5 text-left transition-[background-color,color,box-shadow] duration-[var(--dur-fast)] ease-[var(--ease)] ${
                  screen === selected
                    ? "bg-[var(--surface)] font-medium text-[var(--primary)] shadow-[var(--elev-neumorph)]! hover:bg-[var(--surface)] hover:shadow-[var(--elev-neumorph)]!"
                    : "bg-transparent text-[var(--text-2)] shadow-none hover:bg-transparent active:bg-transparent hover:text-[var(--text)]"
                }`}
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
