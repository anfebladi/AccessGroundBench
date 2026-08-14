import {
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";

export function useOnionDivider(initialPct = 50) {
  const [onionPct, setOnionPct] = useState(initialPct);
  const dragging = useRef(false);

  const dividerHandlers = {
    onPointerDown: (e: ReactPointerEvent<HTMLDivElement>) => {
      dragging.current = true;
      e.currentTarget.setPointerCapture(e.pointerId);
    },
    onPointerMove: (e: ReactPointerEvent<HTMLDivElement>) => {
      if (!dragging.current) return;
      const rect = e.currentTarget.parentElement?.getBoundingClientRect();
      if (rect)
        setOnionPct(
          Math.max(
            0,
            Math.min(100, ((e.clientX - rect.left) / rect.width) * 100),
          ),
        );
    },
    onPointerUp: () => {
      dragging.current = false;
    },
    onPointerCancel: () => {
      dragging.current = false;
    },
    onKeyDown: (e: ReactKeyboardEvent<HTMLDivElement>) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      e.preventDefault();
      const dir = e.key === "ArrowLeft" ? -2 : 2;
      setOnionPct((pct) => Math.max(0, Math.min(100, pct + dir)));
    },
  };

  return { onionPct, dividerHandlers };
}

export type OnionDividerHandlers = ReturnType<typeof useOnionDivider>["dividerHandlers"];
