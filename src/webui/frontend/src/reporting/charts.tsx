import React from "react";
import "./reporting.module.css";

export type ChartRow = {
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

const W = 760;
const PAD_R = 16;
const BAR = 16;
const AXIS_H = 22;
const esc = (value: unknown) => String(value ?? "");

function Frame({
  label,
  height,
  children,
}: {
  label: string;
  height: number;
  children: React.ReactNode;
}) {
  return (
    <svg
      className="chart"
      viewBox={`0 0 ${W} ${height}`}
      role="img"
      aria-label={label}
      preserveAspectRatio="xMinYMin meet"
    >
      <title>{label}</title>
      {children}
    </svg>
  );
}

function ticks(scale: (value: number) => number, height: number) {
  return [0, 0.25, 0.5, 0.75, 1].map((tick) => (
    <React.Fragment key={tick}>
      <line
        className="chart-grid"
        x1={scale(tick)}
        y1="0"
        x2={scale(tick)}
        y2={height}
      />
      <text
        className="chart-axis-label"
        x={scale(tick)}
        y={height + 15}
        textAnchor="middle"
      >
        {Math.round(tick * 100)}%
      </text>
    </React.Fragment>
  ));
}

function barPath(
  x0: number,
  y: number,
  width: number,
  height: number,
  radius = 4,
) {
  const w = Math.max(0, width);
  if (!w) return "";
  const r = Math.min(radius, w);
  const x1 = x0 + w;
  return `M${x0},${y} H${x1 - r} A${r},${r} 0 0 1 ${x1},${y + r} V${y + height - r} A${r},${r} 0 0 1 ${x1 - r},${y + height} H${x0} Z`;
}
function leftBarPath(
  x0: number,
  y: number,
  width: number,
  height: number,
  radius = 4,
) {
  const w = Math.max(0, width);
  if (!w) return "";
  const r = Math.min(radius, w);
  const x1 = x0 - w;
  return `M${x0},${y} H${x1 + r} A${r},${r} 0 0 0 ${x1},${y + r} V${y + height - r} A${r},${r} 0 0 0 ${x1 + r},${y + height} H${x0} Z`;
}

export function AccuracyChart({ rows }: { rows: ChartRow[] }) {
  if (!rows.length) return null;
  const band = 30,
    height = rows.length * band + AXIS_H + 10,
    gutter = 168,
    x0 = gutter,
    x1 = W - PAD_R - 54;
  const scale = (value: number) =>
    x0 + Math.max(0, Math.min(1, value)) * (x1 - x0);
  return (
    <Frame label="Overall accuracy by model" height={height}>
      {ticks(scale, rows.length * band)}
      <line
        className="chart-rule"
        x1={x0}
        y1="0"
        x2={x0}
        y2={rows.length * band}
      />
      {rows.map((row, i) => {
        const value = Number(row.value) || 0;
        const y = i * band + (band - BAR) / 2;
        const end = scale(value);
        return (
          <React.Fragment key={`${row.label}-${i}`}>
            <text
              className="chart-name"
              x={gutter - 10}
              y={i * band + band / 2 + 4}
              textAnchor="end"
            >
              {esc(row.label)}
            </text>
            <path
              className="chart-mark"
              d={barPath(x0, y, end - x0, BAR)}
              fill="var(--viz-blue)"
            />
            <text
              className="chart-value"
              x={end + 8}
              y={i * band + band / 2 + 4}
            >
              {(value * 100).toFixed(1)}%
            </text>
          </React.Fragment>
        );
      })}
    </Frame>
  );
}

export function ReachabilityChart({ rows }: { rows: ChartRow[] }) {
  if (!rows.length) return null;
  const band = 34,
    height = rows.length * band + AXIS_H + 10,
    gutter = 168,
    x0 = gutter,
    x1 = W - PAD_R - 54;
  const scale = (value: number) =>
    x0 + Math.max(0, Math.min(1, value)) * (x1 - x0);
  return (
    <Frame
      label="Target reachability by profile, with 95% confidence intervals"
      height={height}
    >
      {ticks(scale, rows.length * band)}
      <line
        className="chart-rule"
        x1={x0}
        y1="0"
        x2={x0}
        y2={rows.length * band}
      />
      {rows.map((row, i) => {
        const value = Number(row.value) || 0,
          lo = scale(Number(row.lo) || 0),
          hi = scale(Number(row.hi) || 0),
          y = i * band + (band - BAR) / 2,
          end = scale(value);
        return (
          <React.Fragment key={`${row.label}-${i}`}>
            <text
              className="chart-name"
              x={gutter - 10}
              y={i * band + band / 2 + 4}
              textAnchor="end"
            >
              {esc(row.label)}
            </text>
            <path
              className="chart-mark"
              d={barPath(x0, y, end - x0, BAR)}
              fill="var(--viz-blue)"
            />
            <g stroke="var(--text-2)" strokeWidth="1.5">
              <line
                x1={lo}
                y1={i * band + band / 2}
                x2={hi}
                y2={i * band + band / 2}
              />
              <line x1={lo} y1={y + 3} x2={lo} y2={y + BAR - 3} />
              <line x1={hi} y1={y + 3} x2={hi} y2={y + BAR - 3} />
            </g>
            <text
              className="chart-value"
              x={Math.max(end, hi) + 8}
              y={i * band + band / 2 + 4}
            >
              {(value * 100).toFixed(1)}%
            </text>
          </React.Fragment>
        );
      })}
    </Frame>
  );
}

export function DumbbellChart({ rows }: { rows: ChartRow[] }) {
  if (!rows.length) return null;
  const band = 30,
    height = rows.length * band + AXIS_H + 10,
    gutter = 190,
    x0 = gutter,
    x1 = W - PAD_R - 56;
  const scale = (v: number) => x0 + Math.max(0, Math.min(1, v)) * (x1 - x0);
  return (
    <Frame label="Baseline versus profile accuracy per model" height={height}>
      {ticks(scale, rows.length * band)}
      {rows.map((row, i) => {
        const from = scale(Number(row.from) || 0),
          to = scale(Number(row.to) || 0),
          y = i * band + band / 2,
          delta = (Number(row.to) || 0) - (Number(row.from) || 0);
        return (
          <g
            className="chart-row"
            opacity={row.underpowered ? 0.5 : 1}
            key={`${row.label}-${i}`}
          >
            <text
              className="chart-name"
              x={gutter - 10}
              y={y + 4}
              textAnchor="end"
            >
              {esc(row.label)}
              {row.underpowered ? " †" : ""}
            </text>
            <line
              x1={from}
              y1={y}
              x2={to}
              y2={y}
              stroke="var(--text-2)"
              strokeWidth="2"
              strokeLinecap="round"
            />
            <circle
              cx={from}
              cy={y}
              r="5"
              fill="var(--viz-blue)"
              stroke="var(--surface)"
              strokeWidth="2"
            />
            <circle
              cx={to}
              cy={y}
              r="5"
              fill="var(--viz-orange)"
              stroke="var(--surface)"
              strokeWidth="2"
            />
            <text
              className="chart-value"
              x={W - PAD_R}
              y={y + 4}
              textAnchor="end"
            >
              {delta >= 0 ? "+" : ""}
              {(delta * 100).toFixed(1)}
            </text>
          </g>
        );
      })}
    </Frame>
  );
}

export function DiscordantChart({ rows }: { rows: ChartRow[] }) {
  if (!rows.length) return null;
  const band = 36,
    annotation = 190,
    height = rows.length * band + AXIS_H + 10,
    gutter = 168,
    x0 = gutter,
    x1 = W - PAD_R - annotation,
    centre = (x0 + x1) / 2,
    max = Math.max(
      1,
      ...rows.map((row) => Math.max(row.left || 0, row.right || 0)),
    ),
    arm = centre - x0 - 32,
    scale = (v: number) => (v / max) * arm;
  return (
    <Frame
      label="Discordant pairs per profile: broken by the profile versus recovered"
      height={height}
    >
      <line
        className="chart-baseline"
        x1={centre}
        y1="0"
        x2={centre}
        y2={rows.length * band}
      />
      {rows.map((row, i) => {
        const y = i * band + (band - BAR) / 2,
          mid = i * band + band / 2 + 4,
          left = row.left || 0,
          right = row.right || 0;
        return (
          <React.Fragment key={`${row.label}-${i}`}>
            <text
              className="chart-name"
              x={gutter - 10}
              y={mid}
              textAnchor="end"
            >
              {esc(row.label)}
            </text>
            <path
              className="chart-mark"
              d={leftBarPath(centre - 1, y, scale(left), BAR)}
              fill="var(--viz-red)"
            />
            <path
              className="chart-mark"
              d={barPath(centre + 1, y, scale(right), BAR)}
              fill="var(--viz-blue)"
            />
            <text
              className="chart-value"
              x={centre - scale(left) - 6}
              y={mid}
              textAnchor="end"
            >
              {left}
            </text>
            <text className="chart-value" x={centre + scale(right) + 6} y={mid}>
              {right}
            </text>
            {row.significant ? (
              <rect
                x={x1 + 8}
                y={mid - 8}
                width="9"
                height="9"
                fill="var(--text)"
              />
            ) : (
              <rect
                x={x1 + 8.5}
                y={mid - 7.5}
                width="8"
                height="8"
                fill="none"
                stroke="var(--text-2)"
                strokeWidth="1.5"
              />
            )}
            <text x={x1 + 23} y={mid}>
              {esc(row.annotation)}
            </text>
          </React.Fragment>
        );
      })}
      <text
        className="chart-axis-label"
        x={centre - 8}
        y={rows.length * band + 15}
        textAnchor="end"
      >
        broke it (b)
      </text>
      <text
        className="chart-axis-label"
        x={centre + 8}
        y={rows.length * band + 15}
      >
        recovered (c)
      </text>
    </Frame>
  );
}

export function DirectionChart({ rows }: { rows: ChartRow[] }) {
  if (!rows.length) return null;
  const band = 34,
    height = rows.length * band + AXIS_H + 10,
    gutter = 168,
    x0 = gutter,
    x1 = W - PAD_R - 92,
    total = Math.max(
      1,
      ...rows.map((row) => (row.down || 0) + (row.up || 0) + (row.tied || 0)),
    ),
    scale = (v: number) => (v / total) * (x1 - x0);
  return (
    <Frame
      label="Direction of change per profile across models"
      height={height}
    >
      {rows.map((row, i) => {
        const y = i * band + (band - BAR) / 2,
          mid = i * band + band / 2 + 4,
          segments = [
            { value: row.down || 0, fill: "var(--viz-red)" },
            { value: row.tied || 0, fill: "var(--viz-neutral)" },
            { value: row.up || 0, fill: "var(--viz-blue)" },
          ];
        let cursor = x0;
        return (
          <React.Fragment key={`${row.label}-${i}`}>
            <text
              className="chart-name"
              x={gutter - 10}
              y={mid}
              textAnchor="end"
            >
              {esc(row.label)}
            </text>
            {segments.map((segment, j) => {
              const width = scale(segment.value),
                start = j === 0 ? cursor : cursor + 2,
                w = Math.max(0, j === segments.length - 1 ? width : width - 2);
              cursor += width;
              return (
                <rect
                  key={j}
                  className="chart-mark"
                  x={start}
                  y={y}
                  width={w}
                  height={BAR}
                  fill={segment.fill}
                />
              );
            })}
            <text
              className="chart-value"
              x={W - PAD_R}
              y={mid}
              textAnchor="end"
            >
              p = {esc(row.p)}
            </text>
          </React.Fragment>
        );
      })}
    </Frame>
  );
}

export function Legend({
  items,
}: {
  items: Array<{ color: string; label: string; shape?: "hollow" }>;
}) {
  return (
    <div className="chart-legend">
      {items.map((item) => (
        <span
          className="legend-item"
          style={{ color: item.color }}
          key={item.label}
        >
          <span
            className={`legend-swatch${item.shape === "hollow" ? "" : " filled"}`}
          />
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
