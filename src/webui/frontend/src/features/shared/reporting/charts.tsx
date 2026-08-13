import React, { useEffect, useState } from "react";
import { Bar } from "@nivo/bar";
import { ScatterPlot } from "@nivo/scatterplot";
import { ScrollArea } from "../../../components/ui/scroll-area";
import "./reporting.module.css";

if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
}

export type ChartRow = {
  id?: string;
  label: string;
  value?: number;
  from?: number;
  to?: number;
  lo?: number;
  hi?: number;
  left?: number;
  right?: number;
  down?: number;
  up?: number;
  tied?: number;
  p?: string;
  underpowered?: boolean;
  significant?: boolean;
  annotation?: string;
};

const WIDTH = 760;
const MARGIN = { top: 18, right: 92, bottom: 38, left: 168 };
const DUMBBELL_MARGIN = { ...MARGIN, right: 180 };
const TICKS = [0, 0.25, 0.5, 0.75, 1];
const COLORS = ["var(--viz-blue)", "var(--viz-orange)", "var(--viz-red)"];
type ChartTone = "light" | "dark";
type ChartTheme = {
  text: { fill: string; fontSize: number };
  axis: { ticks: { text: { fill: string } }; legend: { text: { fill: string } } };
  grid: { line: { stroke: string; strokeWidth: number } };
  tooltip: { container: { background: string; color: string } };
};

function useMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(query.matches);
    update();
    query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, []);
  return !reduced;
}

function validRows(rows: ChartRow[]) {
  const used = new Set<string>();
  return rows
    .filter((row) => row && typeof row.label === "string" && row.label.length > 0)
    .map((row, index) => {
      const base = row.id || row.label || `row-${index}`;
      let id = base;
      let suffix = 2;
      while (used.has(id)) id = `${base}-${suffix++}`;
      used.add(id);
      return { ...row, id };
    });
}

function ChartFrame({
  rows,
  label,
  tone = "light",
  children,
}: {
  rows: ChartRow[];
  label: string;
  tone?: ChartTone;
  children: (height: number, animate: boolean, theme: ChartTheme) => React.ReactNode;
}) {
  const animate = useMotion();
  const usable = validRows(rows);
  if (!usable.length) return <div className="chart-empty">No valid data available.</div>;
  const height = Math.max(240, usable.length * 42 + MARGIN.top + MARGIN.bottom);
  return (
    <div className={`chart-shell chart-${tone}`} role="img" aria-label={label} data-chart-label={label} data-chart-tone={tone}>
      <ScrollArea className="max-h-[560px]">
        <div style={{ width: WIDTH, height }} data-chart-target>
          {children(height, animate, tone === "dark" ? darkTheme : lightTheme)}
        </div>
      </ScrollArea>
    </div>
  );
}

const lightTheme = {
  text: { fill: "var(--text-2)", fontSize: 12 },
  axis: { ticks: { text: { fill: "var(--text-2)" } }, legend: { text: { fill: "var(--text-2)" } } },
  grid: { line: { stroke: "var(--border-subtle)", strokeWidth: 1 } },
  tooltip: { container: { background: "var(--surface-2)", color: "var(--text)" } },
};
const darkTheme = {
  text: { fill: "var(--on-dark-muted)", fontSize: 12 },
  axis: { ticks: { text: { fill: "var(--on-dark-muted)" } }, legend: { text: { fill: "var(--on-dark-muted)" } } },
  grid: { line: { stroke: "var(--on-dark-border)", strokeWidth: 1 } },
  tooltip: { container: { background: "var(--surface-2)", color: "var(--text)" } },
};

function bars(rows: ChartRow[], key: string, maxValue?: number) {
  return rows.map((row, index) => ({ id: row.id || `${row.label}-${index}`, label: row.label, [key]: Math.max(0, Math.min(maxValue ?? 1, finiteNumber(row[key as keyof ChartRow]))) }));
}

function finiteNumber(value: unknown, fallback = 0) {
  const number = typeof value === "number" ? value : Number(value);
  return Number.isFinite(number) ? number : fallback;
}

type LayerProps = {
  bars?: readonly { key?: string; data?: { indexValue?: string | number; value?: number }; x?: number; y?: number; width?: number; height?: number }[];
  xScale?: (value: number | string) => number | undefined;
  yScale?: (value: number | string) => number | undefined;
};

function scaleCoordinate(scale: NonNullable<LayerProps["xScale"]>, value: number | string) {
  return scale(value) ?? 0;
}

const reachabilityLayer = ({ bars: renderedBars = [], xScale, yScale }: LayerProps) => (
  <g aria-label="95% confidence intervals">
    {renderedBars.map((bar) => {
      const rowLabel = String(bar.data?.indexValue ?? "");
      const source = (reachabilityLayer as unknown as { rows?: ChartRow[] }).rows?.find((row) => row.id === rowLabel);
      if (!source || !xScale) return null;
      const lo = Math.max(0, Math.min(1, finiteNumber(source.lo, finiteNumber(source.value))));
      const hi = Math.max(lo, Math.min(1, finiteNumber(source.hi, finiteNumber(source.value))));
      const y = (bar.y ?? (yScale?.(rowLabel) ?? 0)) + (bar.height ?? 0) / 2;
      const xLo = scaleCoordinate(xScale, lo);
      const xHi = scaleCoordinate(xScale, hi);
      return <g key={rowLabel} className="chart-ci" aria-label={`${rowLabel} 95% confidence interval`}>
        <line x1={xLo} x2={xHi} y1={y} y2={y} />
        <line x1={xLo} x2={xLo} y1={y - 5} y2={y + 5} />
        <line x1={xHi} x2={xHi} y1={y - 5} y2={y + 5} />
      </g>;
    })}
  </g>
);

const dumbbellLayer = ({ xScale, yScale }: LayerProps) => {
  const rows = (dumbbellLayer as unknown as { rows?: ChartRow[] }).rows ?? [];
  const tone = (dumbbellLayer as unknown as { tone?: ChartTone }).tone ?? "light";
  const colors = tone === "dark"
    ? { connector: "rgba(255,255,255,.28)", baseline: "#2a78d6", profile: "#eb6834", outline: "#0a0a0c", label: "#f4f4f5", note: "#a1a1aa" }
    : { connector: "#71717a", baseline: "#2a78d6", profile: "#eb6834", outline: "#ffffff", label: "#18181b", note: "#52525b" };
  if (!xScale || !yScale) return null;
  return <g className="chart-dumbbell-overlay" aria-label="Baseline and profile paired points">
    {rows.map((row) => {
      const baseline = Math.max(0, Math.min(1, finiteNumber(row.from)));
      const profile = Math.max(0, Math.min(1, finiteNumber(row.to)));
      const y = scaleCoordinate(yScale, row.id || row.label) + 0.5;
      const delta = (profile - baseline) * 100;
      const underpowered = Boolean(row.underpowered);
      return <g key={row.id} className={underpowered ? "chart-underpowered" : undefined} style={{ opacity: 1 }}>
        <line className="chart-dumbbell-connector" style={{ stroke: colors.connector, strokeWidth: 2 }} x1={scaleCoordinate(xScale, baseline)} x2={scaleCoordinate(xScale, profile)} y1={y} y2={y} />
        <circle className="chart-dumbbell-baseline" style={{ fill: colors.baseline, stroke: colors.outline, strokeWidth: 2 }} cx={scaleCoordinate(xScale, baseline)} cy={y} r={5} />
        <circle className="chart-dumbbell-profile" style={{ fill: colors.profile, stroke: colors.outline, strokeWidth: 2 }} cx={scaleCoordinate(xScale, profile)} cy={y} r={5} />
        <text className="chart-dumbbell-label" style={{ fill: colors.label, fontSize: 12 }} x={scaleCoordinate(xScale, 1) + 16} y={y + 4}>
          {`${delta >= 0 ? "+" : ""}${delta.toFixed(1)} pp${underpowered ? " †" : ""}`}
          {underpowered && <tspan className="chart-underpowered-note" style={{ fill: colors.note }}> underpowered</tspan>}
        </text>
      </g>;
    })}
  </g>;
};

const discordantLayer = ({ xScale, yScale }: LayerProps) => {
  const rows = (discordantLayer as unknown as { rows?: ChartRow[] }).rows ?? [];
  if (!xScale || !yScale) return null;
  return <g className="chart-discordant-overlay" aria-label="Discordant pair counts and significance">
    {rows.map((row) => {
      const left = Math.max(0, finiteNumber(row.left));
      const right = Math.max(0, finiteNumber(row.right));
      const y = scaleCoordinate(yScale, row.id || row.label) + 0.5;
      const annotation = row.annotation || row.p || "";
      return <g key={row.id || row.label}>
        <text className="chart-direct-label" x={scaleCoordinate(xScale, -left) - 6} y={y + 4} textAnchor="end">{left}</text>
        <text className="chart-direct-label" x={scaleCoordinate(xScale, right) + 6} y={y + 4}>{right}</text>
        {(row.significant || annotation) && (
          <text
            className="chart-significance"
            x={scaleCoordinate(xScale, 0) + 8}
            y={y - 7}
          >
            {`${row.significant ? "*" : ""}${annotation ? ` ${annotation}` : ""}`}
          </text>
        )}
      </g>;
    })}
  </g>;
};

const directionLayer = ({ xScale, yScale }: LayerProps) => {
  const rows = (directionLayer as unknown as { rows?: ChartRow[] }).rows ?? [];
  if (!xScale || !yScale) return null;
  return <g className="chart-direction-overlay" aria-label="Direction segment counts">
    {rows.map((row) => {
      const values = [Math.max(0, finiteNumber(row.down)), Math.max(0, finiteNumber(row.tied)), Math.max(0, finiteNumber(row.up))];
      const y = scaleCoordinate(yScale, row.id || row.label) + 0.5;
      let offset = 0;
      return <g key={row.id || row.label}>
        {values.map((value, index) => {
          const start = offset;
          offset += Math.max(0, value);
          return value > 0 ? <text key={`${row.label}-${index}`} className="chart-direct-label" x={scaleCoordinate(xScale, start + value / 2) + 4} y={y + 4}>{value}</text> : null;
        })}
        {(row.p || row.annotation) && <text className="chart-significance" x={scaleCoordinate(xScale, offset) + 8} y={y + 4}>{row.annotation || `p ${row.p}`}</text>}
      </g>;
    })}
  </g>;
};

export function AccuracyChart({ rows, tone = "light" }: { rows: ChartRow[]; tone?: ChartTone }) {
  const usable = validRows(rows).filter((row) => Number.isFinite(row.value) && row.value! >= 0 && row.value! <= 1);
  const labels = new Map(usable.map((row) => [row.id!, row.label]));
  return (
    <ChartFrame rows={usable} label="Overall accuracy by model" tone={tone}>
      {(height, animate, theme) => (
        <Bar data={bars(usable, "value")} keys={["value"]} indexBy="id" width={WIDTH} height={height}
          layout="horizontal" margin={MARGIN} padding={0.32} valueScale={{ type: "linear", min: 0, max: 1 }} colors={[COLORS[0]]}
          valueFormat={(v) => `${(Number(v) * 100).toFixed(1)}%`} enableLabel enableGridX enableGridY={false}
          axisBottom={{ format: (v) => `${Number(v) * 100}%`, tickValues: TICKS }} axisLeft={{ tickSize: 0, format: (v) => labels.get(String(v)) ?? String(v) }}
          theme={theme} role="img" ariaLabel="Overall accuracy by model" animate={animate} isInteractive />
      )}
    </ChartFrame>
  );
}

export function ReachabilityChart({ rows, tone = "light" }: { rows: ChartRow[]; tone?: ChartTone }) {
  const usable = validRows(rows).filter((row) => Number.isFinite(row.value) && row.value! >= 0 && row.value! <= 1);
  const labels = new Map(usable.map((row) => [row.id!, row.label]));
  (reachabilityLayer as unknown as { rows?: ChartRow[] }).rows = usable;
  return (
    <ChartFrame rows={usable} label="Target reachability by profile, with 95% confidence intervals" tone={tone}>
      {(height, animate, theme) => (
        <Bar data={bars(usable, "value")} keys={["value"]} indexBy="id" width={WIDTH} height={height}
          layout="horizontal" margin={MARGIN} padding={0.32} valueScale={{ type: "linear", min: 0, max: 1 }} colors={[COLORS[0]]}
          valueFormat={(v) => `${(Number(v) * 100).toFixed(1)}%`} enableLabel axisBottom={{ format: (v) => `${Number(v) * 100}%`, tickValues: TICKS }}
          axisLeft={{ tickSize: 0, format: (v) => labels.get(String(v)) ?? String(v) }} theme={theme} role="img" ariaLabel="Target reachability" animate={animate} isInteractive layers={["grid", "axes", "bars", reachabilityLayer as never]} />
      )}
    </ChartFrame>
  );
}

export function DumbbellChart({ rows, tone = "light" }: { rows: ChartRow[]; tone?: ChartTone }) {
  const usable = validRows(rows);
  (dumbbellLayer as unknown as { rows?: ChartRow[] }).rows = usable;
  (dumbbellLayer as unknown as { tone?: ChartTone }).tone = tone;
  const points = usable.flatMap((row) => [
    { id: `${row.id} baseline`, x: Math.max(0, Math.min(1, finiteNumber(row.from))), y: row.id },
    { id: `${row.id} profile`, x: Math.max(0, Math.min(1, finiteNumber(row.to))), y: row.id },
  ]);
  return (
    <ChartFrame rows={usable} label="Baseline versus profile accuracy per model" tone={tone}>
      {(height, animate, theme) => (
        <ScatterPlot data={[{ id: "accuracy", data: points }]} width={WIDTH} height={height} margin={DUMBBELL_MARGIN}
          xScale={{ type: "linear", min: 0, max: 1 }} yScale={{ type: "point" }} colors={[COLORS[0], COLORS[1]]}
          axisBottom={{ format: (v) => `${Number(v) * 100}%`, tickValues: TICKS }} axisLeft={{ tickSize: 0, format: (v) => usable.find((row) => row.id === String(v))?.label ?? String(v) }}
          theme={theme} role="img" ariaLabel="Baseline versus profile accuracy" animate={animate} isInteractive nodeSize={0} layers={["grid", "axes", dumbbellLayer as never]} />
      )}
    </ChartFrame>
  );
}

export function DiscordantChart({ rows }: { rows: ChartRow[] }) {
  const usable = validRows(rows);
  const max = Math.max(1, ...usable.flatMap((row) => [finiteNumber(row.left), finiteNumber(row.right)]));
  const labels = new Map(usable.map((row) => [row.id!, row.label]));
  (discordantLayer as unknown as { rows?: ChartRow[] }).rows = usable;
  return (
    <ChartFrame rows={rows} label="Discordant pairs per profile: broken by the profile versus recovered">
      {(height, animate) => (
        <Bar data={usable.map((r) => ({ id: r.id, broke: -Math.max(0, finiteNumber(r.left)), recovered: Math.max(0, finiteNumber(r.right)) }))}
          keys={["broke", "recovered"]} indexBy="id" width={WIDTH} height={height} layout="horizontal" groupMode="stacked"
          valueScale={{ type: "linear", min: -max, max }} margin={MARGIN} padding={0.3}
          colors={[COLORS[2], COLORS[0]]} enableLabel={false} axisBottom={{ tickValues: 5 }} axisLeft={{ tickSize: 0, format: (v) => labels.get(String(v)) ?? String(v) }}
          theme={lightTheme} role="img" ariaLabel="Discordant pairs" animate={animate} isInteractive layers={["grid", "axes", "bars", discordantLayer as never]} />
      )}
    </ChartFrame>
  );
}

export function DirectionChart({ rows }: { rows: ChartRow[] }) {
  const usable = validRows(rows);
  (directionLayer as unknown as { rows?: ChartRow[] }).rows = usable;
  const labels = new Map(usable.map((row) => [row.id!, row.label]));
  return (
    <ChartFrame rows={rows} label="Direction of change per profile across models">
      {(height, animate) => (
        <Bar data={usable.map((r) => ({ id: r.id, down: Math.max(0, finiteNumber(r.down)), tied: Math.max(0, finiteNumber(r.tied)), up: Math.max(0, finiteNumber(r.up)) }))}
          keys={["down", "tied", "up"]} indexBy="id" width={WIDTH} height={height} layout="horizontal" groupMode="stacked"
          margin={MARGIN} padding={0.3} colors={[COLORS[2], "var(--viz-neutral)", COLORS[0]]} enableLabel
          axisBottom={{ tickValues: 5 }} axisLeft={{ tickSize: 0, format: (v) => labels.get(String(v)) ?? String(v) }} theme={lightTheme} role="img"
          ariaLabel="Direction of change" animate={animate} isInteractive layers={["grid", "axes", "bars", directionLayer as never]} />
      )}
    </ChartFrame>
  );
}

export function Legend({ items }: { items: Array<{ color: string; label: string; shape?: "hollow" }> }) {
  return (
    <div className="chart-legend">
      {items.map((item) => (
        <span className="legend-item" style={{ color: item.color }} key={item.label}>
          <span className={`legend-swatch${item.shape === "hollow" ? "" : " filled"}`} />
          <span style={{ color: "var(--muted)" }}>{item.label}</span>
        </span>
      ))}
    </div>
  );
}

export const accuracyChart = AccuracyChart;
export const reachabilityChart = ReachabilityChart;
export const discordantChart = DiscordantChart;
export const dumbbellChart = DumbbellChart;
export const directionChart = DirectionChart;
export const legend = Legend;
