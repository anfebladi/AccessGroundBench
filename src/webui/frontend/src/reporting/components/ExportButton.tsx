import { useRef } from "react";
import { exportSvgAsPng } from "../../lib/export";

export function ExportButton({ name }: { name: string }) {
  const ref = useRef<HTMLButtonElement>(null);
  return (
    <button
      ref={ref}
      type="button"
      className="secondary small icon-btn"
      data-export-chart={name}
      title="Export chart as PNG"
      aria-label="Export chart as PNG"
      onClick={() => {
        const svg = ref.current?.closest(".card")?.querySelector("svg.chart");
        if (svg instanceof SVGSVGElement) exportSvgAsPng(svg, `${name}.png`);
      }}
    >
      ⇩
    </button>
  );
}
