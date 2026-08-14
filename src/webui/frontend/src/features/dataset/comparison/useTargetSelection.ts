import { useEffect, useState } from "react";
import type { Target } from "../types";

export function useTargetSelection(screen: string, list: Target[]) {
  const [selected, setSelected] = useState<string | null>(null);

  const selectTarget = (text: string) => setSelected(text);
  const clearSelection = () => setSelected(null);

  const moveSelection = (direction: "next" | "prev") => {
    const i = list.findIndex((x) => x.text === selected);
    const next =
      direction === "next"
        ? list[Math.min(list.length - 1, i + 1)]
        : list[Math.max(0, i <= 0 ? 0 : i - 1)];
    if (next) selectTarget(next.text);
  };

  useEffect(() => {
    setSelected(null);
  }, [screen]);

  useEffect(() => {
    if (selected && !list.some((target) => target.text === selected)) {
      setSelected(null);
    }
  }, [list, selected]);

  return { selected, selectTarget, clearSelection, moveSelection };
}
