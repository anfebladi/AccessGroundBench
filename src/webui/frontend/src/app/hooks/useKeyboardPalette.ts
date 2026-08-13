import { useEffect } from "react";
import { TABS, type Tab } from "../navigation";

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;

  return (
    target.tagName === "INPUT" ||
    target.tagName === "TEXTAREA" ||
    target.tagName === "SELECT" ||
    target.isContentEditable ||
    target.contentEditable === "true" ||
    Boolean(target.closest('[contenteditable]:not([contenteditable="false"])'))
  );
}

export function useKeyboardPalette(
  go: (tab: Tab) => void,
  setOpen: (open: boolean) => void,
) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const modifier = event.metaKey || event.ctrlKey;

      if (modifier && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen(true);
        return;
      }

      if (isEditableTarget(event.target) || modifier || event.altKey) return;

      const index = Number(event.key);
      if (index >= 1 && index <= 7) {
        event.preventDefault();
        go(TABS[index - 1]);
      }

      if (event.key === "Escape") setOpen(false);
    };

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [go, setOpen]);
}
