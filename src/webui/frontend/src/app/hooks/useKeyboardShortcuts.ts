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

export function useKeyboardShortcuts(go: (tab: Tab) => void) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const modifier = event.metaKey || event.ctrlKey;

      if (isEditableTarget(event.target) || modifier || event.altKey) return;

      const index = Number(event.key);
      if (index >= 1 && index <= 7) {
        event.preventDefault();
        go(TABS[index - 1]);
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [go]);
}
