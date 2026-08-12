"use strict";

/**
 * PNG export for charts (inline SVG) and the comparison stage (canvas).
 * Entirely client-side -- rasterises through an offscreen canvas and
 * triggers a browser download, no server round-trip and nothing written to
 * disk on the server's behalf.
 *
 * Wiring is delegated rather than per-view: any button anywhere in the page
 * carrying `data-export-chart` or `data-export-canvas` is handled by the one
 * listener initExportButtons() attaches to `document`, so a view only has to
 * add the button -- it never imports this module's internals directly.
 */

function download(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/**
 * Copy computed (resolved) style values from every element in `source` onto
 * the matching element in `clone`, as an inline `style` attribute. A chart
 * SVG carries colour only through CSS (`.chart-dark text { fill: ... }`,
 * `fill="var(--viz-blue)"`) which means nothing once the markup is
 * serialised and rasterised outside the document -- there is no stylesheet
 * or custom-property scope to resolve against. Baking the resolved values in
 * as inline `style` (higher specificity than the SVG's own presentation
 * attributes) is what makes the exported PNG match what's on screen.
 */
function inlineComputedStyles(source, clone) {
  const PROPS = ["fill", "stroke", "stroke-width", "opacity", "font-family", "font-size", "font-weight", "text-anchor"];
  const apply = (s, c) => {
    const cs = getComputedStyle(s);
    c.setAttribute("style", PROPS.map((p) => `${p}:${cs.getPropertyValue(p)}`).join(";"));
  };
  apply(source, clone);
  const srcNodes = source.querySelectorAll("*");
  const cloneNodes = clone.querySelectorAll("*");
  srcNodes.forEach((s, i) => cloneNodes[i] && apply(s, cloneNodes[i]));
}

/** Rasterise an inline `<svg class="chart">` at 2x scale for a crisp export. */
export function exportSvgAsPng(svgEl, filename) {
  const box = svgEl.viewBox?.baseVal;
  const width = box?.width || svgEl.clientWidth || 760;
  const height = box?.height || svgEl.clientHeight || 400;
  const scale = 2;

  const clone = svgEl.cloneNode(true);
  clone.setAttribute("width", width);
  clone.setAttribute("height", height);
  inlineComputedStyles(svgEl, clone);

  // On a dark-surface chart (.chart-dark) the SVG itself paints no
  // background -- the surrounding panel does -- so the raster needs an
  // explicit fill or exported marks would sit on transparency.
  const onDark = svgEl.closest(".chart-dark") !== null;
  const bg = onDark
    ? getComputedStyle(document.documentElement).getPropertyValue("--panel-dark").trim() || "#0a0a0c"
    : getComputedStyle(document.body).backgroundColor || "#ffffff";

  const xml = new XMLSerializer().serializeToString(clone);
  const svgUrl = URL.createObjectURL(new Blob([xml], { type: "image/svg+xml;charset=utf-8" }));

  const img = new Image();
  img.onload = () => {
    const canvas = document.createElement("canvas");
    canvas.width = width * scale;
    canvas.height = height * scale;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.scale(scale, scale);
    ctx.drawImage(img, 0, 0, width, height);
    URL.revokeObjectURL(svgUrl);
    canvas.toBlob((blob) => blob && download(blob, filename));
  };
  img.onerror = () => URL.revokeObjectURL(svgUrl);
  img.src = svgUrl;
}

/** A canvas already holds a bitmap at its native resolution -- no rasterising needed. */
export function exportCanvasAsPng(canvas, filename) {
  canvas.toBlob((blob) => blob && download(blob, filename));
}

/** Composite two same-frame canvases (the onion-skin stage's two layers) into one PNG. */
export function exportCanvasPairAsPng(bottom, top, filename) {
  const canvas = document.createElement("canvas");
  canvas.width = bottom.width;
  canvas.height = bottom.height;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(bottom, 0, 0);
  ctx.drawImage(top, 0, 0, top.width, top.height, 0, 0, bottom.width, bottom.height);
  exportCanvasAsPng(canvas, filename);
}

/**
 * One delegated click listener for every export button in the page, present
 * or future. `data-export-chart="<filename base>"` exports the nearest
 * ancestor `.card`'s `svg.chart`; `data-export-canvas="baseline|profile"`
 * exports compare-stage.js's matching canvas (compositing both layers when
 * the stage is in onion mode, since the top layer alone would just be a
 * clipped sliver). Call once at startup.
 */
export function initExportButtons() {
  document.addEventListener("click", (e) => {
    const chartBtn = e.target.closest("[data-export-chart]");
    if (chartBtn) {
      const svg = chartBtn.closest(".card")?.querySelector("svg.chart");
      if (svg) exportSvgAsPng(svg, `${chartBtn.dataset.exportChart}.png`);
      return;
    }

    const canvasBtn = e.target.closest("[data-export-canvas]");
    if (canvasBtn) {
      const which = canvasBtn.dataset.exportCanvas;
      const baseline = document.getElementById("canvas-baseline");
      const profile = document.getElementById("canvas-profile");
      if (!baseline || !profile) return;
      const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
      if (which === "onion" && baseline.width && profile.width) {
        exportCanvasPairAsPng(baseline, profile, `comparison-${stamp}.png`);
      } else if (which === "baseline" && baseline.width) {
        exportCanvasAsPng(baseline, `baseline-${stamp}.png`);
      } else if (which === "profile" && profile.width) {
        exportCanvasAsPng(profile, `profile-${stamp}.png`);
      }
    }
  });
}
