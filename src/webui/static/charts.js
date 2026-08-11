"use strict";

/**
 * Inline-SVG chart primitives. No library, no CDN -- the UI ships as static
 * package data and a charting dependency would mean a build step.
 *
 * Every chart follows the same rules: thin marks capped well under the band
 * height, a 4px rounded data-end square at the baseline, hairline recessive
 * gridlines, values labelled selectively rather than on every mark, and text in
 * ink tokens rather than the series colour. Colours come from the --viz-*
 * custom properties, so a future palette change is a token swap and the SVG
 * needs no JS.
 *
 * Identity is never carried by hue alone: the diverging chart marks
 * significance with a filled vs hollow square, and underpowered rows carry a
 * dagger, so the charts survive greyscale print and colour-vision deficiency.
 */

import { escapeHtml } from "./ui.js";

const W = 760;              // viewBox width; the chart scales to its container
const PAD_R = 16;
const BAR = 16;             // mark thickness, capped well under the band
const RADIUS = 4;
const AXIS_H = 22;

function svg(height, label, body) {
  return `<svg class="chart" viewBox="0 0 ${W} ${height}" role="img"
     aria-label="${escapeHtml(label)}" preserveAspectRatio="xMinYMin meet">
     <title>${escapeHtml(label)}</title>${body}</svg>`;
}

/** Horizontal bar with the data-end rounded and the baseline end square. */
function barPath(x0, y, width, height, r = RADIUS) {
  const w = Math.max(0, width);
  const rr = Math.min(r, w);
  if (w <= 0) return "";
  const x1 = x0 + w;
  return `M${x0},${y} H${x1 - rr} A${rr},${rr} 0 0 1 ${x1},${y + rr}`
    + ` V${y + height - rr} A${rr},${rr} 0 0 1 ${x1 - rr},${y + height} H${x0} Z`;
}

/** Mirror of barPath, for the left arm of a diverging chart. */
function barPathLeft(x0, y, width, height, r = RADIUS) {
  const w = Math.max(0, width);
  const rr = Math.min(r, w);
  if (w <= 0) return "";
  const x1 = x0 - w;
  return `M${x0},${y} H${x1 + rr} A${rr},${rr} 0 0 0 ${x1},${y + rr}`
    + ` V${y + height - rr} A${rr},${rr} 0 0 0 ${x1 + rr},${y + height} H${x0} Z`;
}

function tickValues(max) {
  const steps = [0, 0.25, 0.5, 0.75, 1];
  return steps.map((s) => s * max);
}

// ---------------------------------------------------------------- bar + CI

/**
 * Reachability: one measure per profile, so a single series and no legend --
 * the card title already says what is plotted. Wilson bounds ride each bar as
 * an error bar, because a proportion over ~150 targets without its interval
 * invites over-reading small gaps.
 */
export function reachabilityChart(rows, { gutter = 168 } = {}) {
  if (!rows.length) return "";
  const band = 34;
  const height = rows.length * band + AXIS_H + 10;
  const valueGutter = 54;
  const x0 = gutter;
  const x1 = W - PAD_R - valueGutter;
  const scale = (v) => x0 + Math.max(0, Math.min(1, v)) * (x1 - x0);

  const grid = tickValues(1).map((t) => `
    <line class="chart-grid" x1="${scale(t)}" y1="0" x2="${scale(t)}" y2="${rows.length * band}" />
    <text class="chart-axis-label" x="${scale(t)}" y="${rows.length * band + 15}"
          text-anchor="middle">${Math.round(t * 100)}%</text>`).join("");

  const bars = rows.map((r, i) => {
    const y = i * band + (band - BAR) / 2;
    const end = scale(r.value);
    const lo = scale(r.lo);
    const hi = scale(r.hi);
    const labelX = Math.max(end, hi) + 8;
    return `
      <text class="chart-name" x="${gutter - 10}" y="${i * band + band / 2 + 4}" text-anchor="end">${escapeHtml(r.label)}</text>
      <path d="${barPath(x0, y, end - x0, BAR)}" fill="var(--viz-blue)" />
      <g stroke="var(--text-2)" stroke-width="1.5">
        <line x1="${lo}" y1="${i * band + band / 2}" x2="${hi}" y2="${i * band + band / 2}" />
        <line x1="${lo}" y1="${y + 3}" x2="${lo}" y2="${y + BAR - 3}" />
        <line x1="${hi}" y1="${y + 3}" x2="${hi}" y2="${y + BAR - 3}" />
      </g>
      <text class="chart-value" x="${labelX}" y="${i * band + band / 2 + 4}">${(r.value * 100).toFixed(1)}%</text>`;
  }).join("");

  return svg(height, "Target reachability by profile, with 95% confidence intervals",
    `${grid}<line class="chart-rule" x1="${x0}" y1="0" x2="${x0}" y2="${rows.length * band}" />${bars}`);
}

// ------------------------------------------------------------- diverging

/**
 * Discordant pairs: targets the profile broke (b) against targets it recovered
 * (c). A diverging form is the honest one here -- the test is entirely about
 * which arm is heavier, and two separate bars would hide that.
 */
export function discordantChart(rows, { gutter = 168 } = {}) {
  if (!rows.length) return "";
  const band = 36;
  const annotation = 190;
  const height = rows.length * band + AXIS_H + 10;
  const x0 = gutter;
  const x1 = W - PAD_R - annotation;
  const centre = (x0 + x1) / 2;
  const maxArm = Math.max(1, ...rows.map((r) => Math.max(r.left, r.right)));
  // Each arm stops short of its half-width so the count sitting outside the bar
  // end always has room; at full width the longest bar's label collided with
  // the row label.
  const arm = (centre - x0) - 32;
  const scale = (v) => (v / maxArm) * arm;

  const bars = rows.map((r, i) => {
    const y = i * band + (band - BAR) / 2;
    const mid = i * band + band / 2 + 4;
    // 1px inset each side of the axis keeps a 2px surface gap between the arms.
    const marker = r.significant
      ? `<rect x="${x1 + 8}" y="${mid - 8}" width="9" height="9" fill="var(--text)" />`
      : `<rect x="${x1 + 8.5}" y="${mid - 7.5}" width="8" height="8" fill="none" stroke="var(--text-2)" stroke-width="1.5" />`;
    return `
      <text class="chart-name" x="${gutter - 10}" y="${mid}" text-anchor="end">${escapeHtml(r.label)}</text>
      <path d="${barPathLeft(centre - 1, y, scale(r.left), BAR)}" fill="var(--viz-red)" />
      <path d="${barPath(centre + 1, y, scale(r.right), BAR)}" fill="var(--viz-blue)" />
      <text class="chart-value" x="${centre - scale(r.left) - 6}" y="${mid}" text-anchor="end">${r.left}</text>
      <text class="chart-value" x="${centre + scale(r.right) + 6}" y="${mid}">${r.right}</text>
      ${marker}
      <text x="${x1 + 23}" y="${mid}">${escapeHtml(r.annotation)}</text>`;
  }).join("");

  return svg(height, "Discordant pairs per profile: broken by the profile versus recovered",
    `<line class="chart-baseline" x1="${centre}" y1="0" x2="${centre}" y2="${rows.length * band}" />
     ${bars}
     <text class="chart-axis-label" x="${centre - 8}" y="${rows.length * band + 15}" text-anchor="end">broke it (b)</text>
     <text class="chart-axis-label" x="${centre + 8}" y="${rows.length * band + 15}">recovered (c)</text>`);
}

// -------------------------------------------------------------- dumbbell

/**
 * Baseline accuracy to profile accuracy, one row per model. The connector is
 * the finding; the two dots are only its endpoints, which is why they carry a
 * surface ring rather than a stroke -- they overlap constantly at ceiling.
 */
export function dumbbellChart(rows, { gutter = 190 } = {}) {
  if (!rows.length) return "";
  const band = 30;
  const height = rows.length * band + AXIS_H + 10;
  const x0 = gutter;
  const x1 = W - PAD_R - 56;
  const scale = (v) => x0 + Math.max(0, Math.min(1, v)) * (x1 - x0);

  const grid = tickValues(1).map((t) => `
    <line class="chart-grid" x1="${scale(t)}" y1="0" x2="${scale(t)}" y2="${rows.length * band}" />
    <text class="chart-axis-label" x="${scale(t)}" y="${rows.length * band + 15}"
          text-anchor="middle">${Math.round(t * 100)}%</text>`).join("");

  const marks = rows.map((r, i) => {
    const y = i * band + band / 2;
    const a = scale(r.from);
    const b = scale(r.to);
    // Underpowered rows keep a dagger, so the caveat survives greyscale and is
    // not left to a colour difference nobody is obliged to perceive.
    const dim = r.underpowered ? ' opacity="0.5"' : "";
    const flag = r.underpowered ? " †" : "";
    const delta = r.to - r.from;
    const deltaText = `${delta >= 0 ? "+" : ""}${(delta * 100).toFixed(1)}`;
    return `
      <g${dim}>
        <text class="chart-name" x="${gutter - 10}" y="${y + 4}" text-anchor="end">${escapeHtml(r.label)}${flag}</text>
        <line x1="${a}" y1="${y}" x2="${b}" y2="${y}" stroke="var(--text-2)" stroke-width="2" stroke-linecap="round" />
        <circle cx="${a}" cy="${y}" r="5" fill="var(--viz-blue)" stroke="var(--surface)" stroke-width="2" />
        <circle cx="${b}" cy="${y}" r="5" fill="var(--viz-orange)" stroke="var(--surface)" stroke-width="2" />
        <text class="chart-value" x="${W - PAD_R}" y="${y + 4}" text-anchor="end">${deltaText}</text>
      </g>`;
  }).join("");

  return svg(height, "Baseline versus profile accuracy per model", `${grid}${marks}`);
}

// ---------------------------------------------------------------- stacked

/**
 * How many models moved down, up, or not at all. Diverging by construction, so
 * the neutral tied segment sits between the two poles rather than beside them.
 */
export function directionChart(rows, { gutter = 168 } = {}) {
  if (!rows.length) return "";
  const band = 34;
  const height = rows.length * band + AXIS_H + 10;
  const x0 = gutter;
  const x1 = W - PAD_R - 92;
  const total = Math.max(1, ...rows.map((r) => r.down + r.up + r.tied));
  const scale = (v) => (v / total) * (x1 - x0);

  const bars = rows.map((r, i) => {
    const y = i * band + (band - BAR) / 2;
    const mid = i * band + band / 2 + 4;
    // All three fills are mid-lightness, so white ink clears contrast on each.
    const segments = [
      ["down", r.down, "var(--viz-red)", "#ffffff"],
      ["tied", r.tied, "var(--viz-neutral)", "#ffffff"],
      ["up", r.up, "var(--viz-blue)", "#ffffff"],
    ].filter(([, v]) => v > 0);

    let cursor = x0;
    const paths = segments.map(([, value, fill, ink], idx) => {
      const width = scale(value);
      // A 2px surface gap does the separating; no stroke is drawn around a mark.
      const start = idx === 0 ? cursor : cursor + 2;
      const w = Math.max(0, idx === 0 ? width : width - 2);
      cursor += width;
      const d = idx === segments.length - 1
        ? barPath(start, y, w, BAR)
        : `M${start},${y} h${w} v${BAR} h${-w} Z`;

      // Direct label inside the segment, when it fits. This is not decoration:
      // the neutral "tied" fill sits below the CVD separation gate against the
      // red "down" fill on the dark surface, so hue alone cannot be trusted to
      // tell the two apart. The number carries the identity instead. Ink colour
      // is picked by the fill's luminance so it always clears contrast.
      const label = String(value);
      const fits = w >= label.length * 8 + 10;
      const text = fits
        ? `<text x="${start + w / 2}" y="${mid - 1}" text-anchor="middle"
                 fill="${ink}" font-weight="500">${label}</text>`
        : "";
      return `<path d="${d}" fill="${fill}" />${text}`;
    }).join("");

    return `
      <text class="chart-name" x="${gutter - 10}" y="${mid}" text-anchor="end">${escapeHtml(r.label)}</text>
      ${paths}
      <text class="chart-value" x="${W - PAD_R}" y="${mid}" text-anchor="end">p = ${escapeHtml(r.p)}</text>`;
  }).join("");

  return svg(height, "Direction of change per profile across models", bars);
}

// ----------------------------------------------------------------- legend

export function legend(items) {
  return `<div class="chart-legend">${items.map(({ color, label, shape }) => `
    <span class="legend-item" style="color:${color}">
      <span class="legend-swatch${shape === "hollow" ? "" : " filled"}"></span>
      <span style="color:var(--muted)">${escapeHtml(label)}</span>
    </span>`).join("")}</div>`;
}
