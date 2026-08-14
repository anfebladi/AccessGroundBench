import { useRef } from "react";
import { exportSvgAsPng } from "../../../../lib/export";

export function ExportButton({
  name,
  targetId,
}: {
  name: string;
  targetId: string;
}) {
  const ref = useRef<HTMLButtonElement>(null);
  return (
    <button
      ref={ref}
      type="button"
      className="inline-flex size-8 cursor-pointer items-center justify-center rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] text-sm hover:bg-[var(--surface-2)]"
      data-export-chart={name}
      title="Export chart as PNG"
      aria-label="Export chart as PNG"
      onClick={() => {
        const target = targetId
          ? document.getElementById(targetId)
          : undefined;
        const svg = target?.querySelector("svg");
        if (svg instanceof SVGSVGElement) exportSvgAsPng(svg, `${name}.png`);
      }}
    >
      ⇩
    </button>
  );
}
