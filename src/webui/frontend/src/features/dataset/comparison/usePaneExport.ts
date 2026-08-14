import { type RefObject } from "react";
import { exportCanvasAsPng, exportCanvasPairAsPng } from "../../../lib/export";

export function usePaneExport() {
  const exportPane = (
    wrap: RefObject<HTMLDivElement | null>,
    filename: string,
  ) => {
    const canvas = wrap.current?.querySelector("canvas");
    if (canvas) exportCanvasAsPng(canvas, filename);
  };

  /* The onion panes are two stacked canvases; the divider is a CSS clip, so the
     composite has to be re-cut at the same reveal fraction on export. */
  const exportOnionComposite = (
    onionWrap: RefObject<HTMLDivElement | null>,
    onionPct: number,
  ) => {
    const canvases = onionWrap.current?.querySelectorAll("canvas");
    if (canvases?.length === 2)
      exportCanvasPairAsPng(
        canvases[0],
        canvases[1],
        "onion-composite.png",
        onionPct / 100,
      );
  };

  return { exportPane, exportOnionComposite };
}
