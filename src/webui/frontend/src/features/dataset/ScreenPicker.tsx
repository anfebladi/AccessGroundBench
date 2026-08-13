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
    <div className="picker" style={{ flex: "0 0 15rem" }}>
      <Input
        id="screen-filter"
        type="search"
        placeholder="Filter screens"
        aria-label="Filter screens"
        value={filter}
        onChange={(event) => onFilter(event.target.value)}
      />
      <ul id="screen-list" className="list picker-list">
        {visible.length ? (
          visible.map((screen) => (
            <li
              data-screen={screen}
              className={screen === selected ? "selected" : ""}
              key={screen}
            >
              <Button
                type="button"
                className="screen-picker-button"
                aria-label={screen}
                onClick={() => onSelect(screen)}
              >
                {screen}
              </Button>
            </li>
          ))
        ) : (
          <li className="muted" style={{ cursor: "default" }}>
            No matching screens
          </li>
        )}
      </ul>
    </div>
  );
}
