"use strict";

/**
 * The screen-comparison instrument: baseline against one accessibility
 * profile, side by side or as an onion-skin overlay, with synchronised
 * zoom/pan and a target list wired bidirectionally to the boxes drawn on
 * the canvases.
 *
 * Pure canvas/DOM module. view-dataset.js owns the screen list, capture
 * warnings and data fetching; once it has targets/labels for a screen it
 * calls renderComparisonStage() with everything already resolved, and this
 * module owns `#screen-browser` and `#compare-overlay-toggles` and every
 * interaction inside them until the next screen/profile change.
 */

import { imageUrl } from "./api.js";
import {
  cssVar, drawScreenshot, emptyState, html, imageIsDrawable, pct, raw, strokeWidthFor,
} from "./ui.js";
import { icon } from "./icons.js";
import { deleteView, listViews, saveView } from "./storage.js";

export const PROFILES = [
  ["baseline", "Baseline"],
  ["elder_text_heavy", "Text heavy"],
  ["elder_zoom_heavy", "Zoom heavy"],
  ["elder_combo_mid", "Combo mid"],
  ["elder_combo_max", "Combo max"],
  ["colorblind_deuteranomaly", "Deuteranomaly"],
];

const ZOOM_STEP = 0.25;
const ZOOM_MIN = 0.25;
const ZOOM_MAX = 4;
const FIT_MAX_HEIGHT = 640; // px cap under the 62vh budget so short viewports don't blow past it

// Everything this module needs to repaint without re-fetching: set fresh by
// renderComparisonStage() on a screen/profile change, then mutated in place
// by the toolbar/list/keyboard handlers below for a same-data repaint.
const stage = {
  dataset: null, screen: null, profile: null, profileLabel: "", isBaselineBoth: false,
  targets: [], present: [], missing: [], profileLabels: [],
  mode: "side-by-side",   // "side-by-side" | "onion"
  zoom: "fit",            // "fit" | number
  onionPct: 50,           // 0-100, how much of baseline is revealed from the left
  evictedOnly: false,
  showBoxes: true,
  showMissing: true,
  selected: null,         // currently highlighted target's text, or null
  onProfileChange: null,
  imgBaseline: null,      // cached Image once loaded (or in flight)
  imgProfile: null,
};

let syncingScroll = false;

// ---------- Public entry point ----------

export function renderComparisonStage(dataset, screen, data, onProfileChange) {
  Object.assign(stage, {
    dataset, screen,
    profile: data.profile,
    profileLabel: data.profileLabel,
    isBaselineBoth: data.isBaselineBoth,
    targets: data.targets,
    present: data.present,
    missing: data.missing,
    profileLabels: data.profileLabels,
    onProfileChange,
    imgBaseline: null,
    imgProfile: null,
    selected: null,
  });
  renderOverlayToggles();
  renderStage();
}

export function renderEmptyStage(message) {
  stage.imgBaseline = null;
  stage.imgProfile = null;
  document.getElementById("compare-overlay-toggles").innerHTML = "";
  document.getElementById("screen-browser").innerHTML = message;
}

// ---------- Overlay toggles (box visibility, independent of the target list) ----------

function renderOverlayToggles() {
  const host = document.getElementById("compare-overlay-toggles");
  host.innerHTML = html`
    <label class="chip-check">
      <input type="checkbox" data-toggle="showBoxes" ${raw(stage.showBoxes ? "checked" : "")} />
      Target boxes
    </label>
    <label class="chip-check">
      <input type="checkbox" data-toggle="showMissing" ${raw(stage.showMissing ? "checked" : "")} />
      Missing targets
    </label>
  `;
  host.querySelectorAll("input[data-toggle]").forEach((box) => {
    box.addEventListener("change", () => {
      stage[box.dataset.toggle] = box.checked;
      paint();
    });
  });
}

// ---------- Stage shell: toolbar, panes, target list ----------

function orderedTargets() {
  const pool = stage.evictedOnly ? stage.missing : stage.targets;
  return [...pool].sort((a, b) => {
    const ay = a.baseline_box?.[1] ?? 0, by = b.baseline_box?.[1] ?? 0;
    if (ay !== by) return ay - by;
    return (a.baseline_box?.[0] ?? 0) - (b.baseline_box?.[0] ?? 0);
  });
}

function isMissing(target) {
  return stage.missing.some((t) => t.text === target.text);
}

function renderStage() {
  const container = document.getElementById("screen-browser");
  const list = orderedTargets();

  container.innerHTML = html`
    <div class="segmented" id="profile-picker" role="group" aria-label="Accessibility profile">
      ${PROFILES.map(([id, label]) => raw(html`
        <button type="button" data-profile="${id}" aria-pressed="${String(id === stage.profile)}">${label}</button>
      `))}
    </div>

    <div class="stage-toolbar">
      <div class="segmented" id="stage-mode-picker" role="group" aria-label="Comparison mode">
        <button type="button" data-mode="side-by-side" aria-pressed="${String(stage.mode === "side-by-side")}">Side by side</button>
        <button type="button" data-mode="onion" aria-pressed="${String(stage.mode === "onion")}">Onion-skin</button>
      </div>
      <div class="segmented" id="stage-zoom" role="group" aria-label="Zoom">
        <button type="button" data-zoom="out" aria-label="Zoom out">&minus;</button>
        <button type="button" data-zoom="fit" aria-pressed="${String(stage.zoom === "fit")}">Fit</button>
        <button type="button" data-zoom="1:1" aria-pressed="${String(stage.zoom === 1)}">1:1</button>
        <button type="button" data-zoom="in" aria-label="Zoom in">+</button>
      </div>
      <label class="chip-check">
        <input type="checkbox" id="stage-evicted-only" ${raw(stage.evictedOnly ? "checked" : "")} />
        Evicted only
      </label>
    </div>

    <div class="stage-toolbar" style="margin-top: var(--space-2);">
      <select id="stage-saved-views" aria-label="Saved views">
        <option value="">Saved views&hellip;</option>
        ${listViews().map((v) => raw(html`<option value="${v.name}">${v.name}</option>`))}
      </select>
      <button type="button" class="secondary small icon-btn" id="stage-view-delete" disabled
              title="Delete saved view" aria-label="Delete saved view">${raw(icon("trash", 13))}</button>
      <input type="text" id="stage-view-name" placeholder="Name this view" style="max-width: 12rem;" />
      <button type="button" class="secondary small icon-btn" id="stage-view-save"
              title="Save current profile/mode/zoom as a view" aria-label="Save current view">${raw(icon("bookmark", 13))}</button>
    </div>

    <div class="stage-body">
      <div class="stage-targets" id="stage-target-list" role="listbox" aria-label="Groundable targets" tabindex="0">
        ${list.length ? list.map((t) => raw(targetRow(t))) : raw(html`
          <p class="muted small" style="padding: var(--space-3);">
            ${stage.evictedOnly ? "Nothing evicted by this profile." : "No targets on this screen."}
          </p>`)}
      </div>
      <div class="stage-panes" id="stage-panes"></div>
    </div>

    ${!stage.isBaselineBoth && stage.missing.length ? raw(html`
      <div class="note note-info" style="margin-top: var(--space-4);">
        <span class="note-label">Note</span>
        <b>${stage.missing.length} target${stage.missing.length === 1 ? "" : "s"} evicted by this profile.</b>
        A target that no longer renders cannot be grounded by any model, so it is
        scored as <code>off_screen</code> rather than as a miss.
      </div>`) : ""}

    <div class="overlay-legend" style="margin-top: var(--space-4);">
      <span class="legend-item" style="color: var(--viz-blue)"><span class="legend-swatch"></span>Groundable target</span>
      <span class="legend-item" style="color: var(--err)"><span class="legend-swatch"></span>Missing from this profile</span>
      <span class="legend-item" style="color: var(--warn)"><span class="legend-swatch filled"></span>Selected</span>
    </div>
  `;

  container.querySelectorAll("button[data-profile]").forEach((btn) => {
    btn.addEventListener("click", () => stage.onProfileChange?.(btn.dataset.profile));
  });
  container.querySelectorAll("button[data-mode]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.dataset.mode === stage.mode) return;
      stage.mode = btn.dataset.mode;
      renderPanes();
    });
  });
  container.querySelectorAll("button[data-zoom]").forEach((btn) => {
    btn.addEventListener("click", () => {
      applyZoomAction(btn.dataset.zoom);
      renderPanes();
    });
  });
  document.getElementById("stage-evicted-only").addEventListener("change", (e) => {
    stage.evictedOnly = e.target.checked;
    renderStage();
  });
  wireSavedViews(container);
  container.querySelectorAll(".stage-target-item").forEach((row) => {
    row.addEventListener("click", () => selectTarget(row.dataset.text, { pan: true }));
  });
  const listHost = document.getElementById("stage-target-list");
  listHost.addEventListener("keydown", (e) => handleListKeydown(e));
  container.addEventListener("keydown", (e) => handleStageKeydown(e));

  renderPanes();
}

// ---------- Saved views (localStorage presets: profile/mode/zoom/evicted) ----------

function wireSavedViews(container) {
  const select = document.getElementById("stage-saved-views");
  const deleteBtn = document.getElementById("stage-view-delete");
  const nameInput = document.getElementById("stage-view-name");
  const saveBtn = document.getElementById("stage-view-save");

  select.addEventListener("change", () => {
    deleteBtn.disabled = !select.value;
    if (select.value) applySavedView(select.value);
  });
  deleteBtn.addEventListener("click", () => {
    if (!select.value) return;
    deleteView(select.value);
    renderStage();
  });
  saveBtn.addEventListener("click", () => {
    const name = nameInput.value.trim();
    if (!name) { nameInput.focus(); return; }
    saveView(name, {
      profile: stage.profile, mode: stage.mode, zoom: stage.zoom,
      evictedOnly: stage.evictedOnly, onionPct: stage.onionPct,
    });
    renderStage();
  });
}

/** Applies a saved preset to the current screen. Only re-fetches (via
 *  onProfileChange) when the saved profile differs from the current one --
 *  mode/zoom/evictedOnly are local state and take effect on the next
 *  renderPanes() either way, whether that comes from a fetch or a plain
 *  local rebuild. */
function applySavedView(name) {
  const view = listViews().find((v) => v.name === name);
  if (!view) return;
  const cfg = view.config || {};
  stage.mode = cfg.mode === "onion" ? "onion" : "side-by-side";
  stage.zoom = cfg.zoom === "fit" ? "fit" : (Number.isFinite(cfg.zoom) ? cfg.zoom : "fit");
  stage.evictedOnly = Boolean(cfg.evictedOnly);
  stage.onionPct = Number.isFinite(cfg.onionPct) ? cfg.onionPct : 50;
  if (cfg.profile && cfg.profile !== stage.profile) {
    stage.onProfileChange?.(cfg.profile);
  } else {
    renderStage();
  }
}

function applyZoomAction(action) {
  if (action === "fit") { stage.zoom = "fit"; return; }
  if (action === "1:1") { stage.zoom = 1; return; }
  const current = stage.zoom === "fit" ? 1 : stage.zoom;
  const next = action === "in" ? current + ZOOM_STEP : current - ZOOM_STEP;
  stage.zoom = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, next));
}

function targetRow(t) {
  const missing = isMissing(t);
  return html`
    <button type="button" class="stage-target-item${raw(missing ? " is-missing" : "")}${raw(t.text === stage.selected ? " is-selected" : "")}"
            data-text="${t.text}" role="option" aria-selected="${String(t.text === stage.selected)}">
      <span class="stage-target-dot" aria-hidden="true"></span>
      <span class="stage-target-text">${t.text}</span>
      ${missing ? raw(`<span class="badge err" style="flex-shrink:0;">evicted</span>`) : ""}
    </button>
  `;
}

// ---------- Panes: side-by-side or onion-skin ----------

function renderPanes() {
  const host = document.getElementById("stage-panes");
  if (!host) return;

  // Toolbar buttons reflect state that renderStage() already computed into
  // the DOM once; flip just the pressed states here rather than a full
  // re-render, which would tear down the panes we are about to redraw anyway.
  document.getElementById("stage-mode-picker")?.querySelectorAll("button").forEach((b) => {
    b.setAttribute("aria-pressed", String(b.dataset.mode === stage.mode));
  });
  document.getElementById("stage-zoom")?.querySelectorAll("button[data-zoom='fit'],button[data-zoom='1:1']").forEach((b) => {
    b.setAttribute("aria-pressed", String(
      (b.dataset.zoom === "fit" && stage.zoom === "fit") || (b.dataset.zoom === "1:1" && stage.zoom === 1)
    ));
  });

  if (stage.mode === "onion") {
    host.innerHTML = html`
      <div class="pane onion-pane-wrap">
        <div class="pane-head">
          <span class="pane-title">Baseline &harr; ${stage.profileLabel}</span>
          <span class="pane-dims" id="dims-baseline"></span>
          <button type="button" class="icon-btn small" data-export-canvas="onion"
                  title="Export composite as PNG" aria-label="Export composite as PNG">${raw(icon("download", 13))}</button>
        </div>
        <div class="pane-canvas onion-pane" id="onion-viewport">
          <div class="skeleton skeleton-block" id="skel-baseline" aria-hidden="true"></div>
          <div class="onion-stack" id="onion-stack" hidden>
            <canvas id="canvas-baseline"></canvas>
            <canvas id="canvas-profile" class="onion-top"></canvas>
            <div class="onion-divider" id="onion-divider" role="slider" tabindex="0"
                 aria-label="Reveal amount" aria-valuemin="0" aria-valuemax="100"
                 aria-valuenow="${stage.onionPct}">
              <span class="onion-grip"></span>
            </div>
          </div>
        </div>
        <p class="image-caption">Drag the divider, or use the arrow keys once it is focused.</p>
      </div>
    `;
    wireOnionDivider();
  } else {
    host.innerHTML = html`
      <div class="pane">
        <div class="pane-head">
          <span class="pane-title">Baseline</span>
          <span class="pane-dims" id="dims-baseline"></span>
          <button type="button" class="icon-btn small" data-export-canvas="baseline"
                  title="Export as PNG" aria-label="Export baseline pane as PNG">${raw(icon("download", 13))}</button>
        </div>
        <div class="pane-canvas" id="viewport-baseline">
          <div class="skeleton skeleton-block" id="skel-baseline" aria-hidden="true"></div>
          <canvas id="canvas-baseline" hidden></canvas>
        </div>
        <p class="image-caption">${stage.targets.length} groundable target${stage.targets.length === 1 ? "" : "s"}</p>
      </div>
      <div class="pane">
        <div class="pane-head">
          <span class="pane-title">${stage.profileLabel}</span>
          <span class="pane-dims" id="dims-profile"></span>
          <button type="button" class="icon-btn small" data-export-canvas="profile"
                  title="Export as PNG" aria-label="Export profile pane as PNG">${raw(icon("download", 13))}</button>
        </div>
        <div class="pane-canvas" id="viewport-profile">
          <div class="skeleton skeleton-block" id="skel-profile" aria-hidden="true"></div>
          <canvas id="canvas-profile" hidden></canvas>
        </div>
        <p class="image-caption">
          ${stage.isBaselineBoth ? "Same capture as the left pane."
            : `${stage.present.length} of ${stage.targets.length} baseline targets still present`
              + (stage.targets.length ? ` (${pct(stage.present.length / stage.targets.length)} reachable)` : "")}
        </p>
      </div>
    `;
    wireScrollSync();
  }

  wireCanvasClick();
  paint();
}

/**
 * Click-to-select on the baseline canvas -- the canvas half of the
 * bidirectional link the target list's own click/keyboard handlers cover
 * the other way. Baseline is the canonical box source (profile boxes only
 * exist for present targets), so hit-testing happens there in both modes.
 */
function wireCanvasClick() {
  const canvas = document.getElementById("canvas-baseline");
  if (!canvas) return;
  canvas.style.cursor = "pointer";
  canvas.addEventListener("click", (e) => {
    if (!imageIsDrawable(stage.imgBaseline)) return;
    const rect = canvas.getBoundingClientRect();
    const img = stage.imgBaseline;
    const nx = ((e.clientX - rect.left) / rect.width) * img.width;
    const ny = ((e.clientY - rect.top) / rect.height) * img.height;
    const pool = stage.evictedOnly ? stage.missing : stage.targets;
    const hit = pool.find((t) => {
      const b = t.baseline_box;
      return b && nx >= b[0] && nx <= b[2] && ny >= b[1] && ny <= b[3];
    });
    if (hit) selectTarget(hit.text, { pan: false });
  });
}

function wireScrollSync() {
  const a = document.getElementById("viewport-baseline");
  const b = document.getElementById("viewport-profile");
  if (!a || !b) return;
  const mirror = (from, to) => {
    if (syncingScroll) return;
    syncingScroll = true;
    const fromRange = from.scrollWidth - from.clientWidth;
    const toRange = to.scrollWidth - to.clientWidth;
    to.scrollLeft = fromRange > 0 ? (from.scrollLeft / fromRange) * toRange : 0;
    const fromRangeY = from.scrollHeight - from.clientHeight;
    const toRangeY = to.scrollHeight - to.clientHeight;
    to.scrollTop = fromRangeY > 0 ? (from.scrollTop / fromRangeY) * toRangeY : 0;
    syncingScroll = false;
  };
  a.addEventListener("scroll", () => mirror(a, b));
  b.addEventListener("scroll", () => mirror(b, a));
}

function wireOnionDivider() {
  const divider = document.getElementById("onion-divider");
  const stack = document.getElementById("onion-stack");
  if (!divider || !stack) return;

  const setPct = (pctValue) => {
    stage.onionPct = Math.min(100, Math.max(0, pctValue));
    divider.style.left = `${stage.onionPct}%`;
    divider.setAttribute("aria-valuenow", String(Math.round(stage.onionPct)));
    const top = document.getElementById("canvas-profile");
    if (top) top.style.clipPath = `inset(0 ${100 - stage.onionPct}% 0 0)`;
  };
  setPct(stage.onionPct);

  let dragging = false;
  const fromEvent = (e) => {
    const rect = stack.getBoundingClientRect();
    const x = (e.touches ? e.touches[0].clientX : e.clientX) - rect.left;
    return (x / rect.width) * 100;
  };
  divider.addEventListener("pointerdown", (e) => {
    dragging = true;
    divider.setPointerCapture(e.pointerId);
  });
  divider.addEventListener("pointermove", (e) => { if (dragging) setPct(fromEvent(e)); });
  divider.addEventListener("pointerup", () => { dragging = false; });
  divider.addEventListener("keydown", (e) => {
    if (e.key === "ArrowLeft") { setPct(stage.onionPct - 2); e.preventDefault(); }
    else if (e.key === "ArrowRight") { setPct(stage.onionPct + 2); e.preventDefault(); }
    else if (e.key === "Home") { setPct(0); e.preventDefault(); }
    else if (e.key === "End") { setPct(100); e.preventDefault(); }
  });
}

// ---------- Painting: image loading, sizing, box overlays ----------

function paneSize(img, wrapperEl) {
  if (stage.zoom === "fit") {
    const maxH = Math.min(window.innerHeight * 0.62, FIT_MAX_HEIGHT);
    const maxW = Math.max((wrapperEl.clientWidth || 320) - 16, 120);
    const scale = Math.min(1, maxW / img.width, maxH / img.height);
    return { width: Math.round(img.width * scale), height: Math.round(img.height * scale) };
  }
  return { width: Math.round(img.width * stage.zoom), height: Math.round(img.height * stage.zoom) };
}

function sizeCanvas(canvas, img, wrapperEl) {
  const { width, height } = paneSize(img, wrapperEl);
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  wrapperEl.classList.toggle("is-zoomed", stage.zoom !== "fit");
}

function boxColor(text, base) {
  return text === stage.selected ? cssVar("--warn", "#a15c00") : base;
}

function decorateBaseline(ctx, img) {
  const dims = document.getElementById("dims-baseline");
  if (dims) dims.textContent = `${img.width} x ${img.height}`;
  if (!stage.showBoxes) return;
  ctx.lineWidth = strokeWidthFor(img);
  const accent = cssVar("--viz-blue", "#2a78d6");
  const err = cssVar("--err", "#b3221a");
  const warn = cssVar("--warn", "#a15c00");
  if (!stage.evictedOnly) {
    for (const t of stage.present) {
      ctx.strokeStyle = t.text === stage.selected ? warn : accent;
      ctx.lineWidth = t.text === stage.selected ? strokeWidthFor(img) * 1.6 : strokeWidthFor(img);
      strokeBox(ctx, t.baseline_box);
    }
  }
  if (stage.showMissing || stage.evictedOnly) {
    for (const t of stage.missing) {
      ctx.strokeStyle = t.text === stage.selected ? warn : err;
      ctx.lineWidth = t.text === stage.selected ? strokeWidthFor(img) * 1.6 : strokeWidthFor(img);
      strokeBox(ctx, t.baseline_box);
    }
  }
}

function decorateProfile(ctx, img) {
  const dims = document.getElementById("dims-profile");
  if (dims) dims.textContent = `${img.width} x ${img.height}`;
  if (!stage.showBoxes || stage.evictedOnly) return;
  ctx.lineWidth = strokeWidthFor(img);
  const accent = cssVar("--viz-blue", "#2a78d6");
  const warn = cssVar("--warn", "#a15c00");
  const wanted = new Set(stage.present.map((t) => t.text));
  for (const rec of stage.profileLabels) {
    const text = (rec.text || "").trim();
    if (!rec.box || !wanted.has(text)) continue;
    ctx.strokeStyle = text === stage.selected ? warn : accent;
    ctx.lineWidth = text === stage.selected ? strokeWidthFor(img) * 1.6 : strokeWidthFor(img);
    strokeBox(ctx, rec.box);
  }
}

function strokeBox(ctx, box) {
  if (!box) return;
  const [x1, y1, x2, y2] = box;
  ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
}

function redrawCached(canvas, img, decorate) {
  const ctx = canvas.getContext("2d");
  canvas.width = img.width;
  canvas.height = img.height;
  ctx.drawImage(img, 0, 0);
  decorate(ctx, img);
}

/**
 * Loads (once) and (re)paints both screenshots into whatever canvases the
 * current mode's markup provides. Called after every state change that
 * affects the pixels -- zoom, mode, toggles, selection -- never re-fetching
 * the image bytes, only redrawing from the cached decoded Image.
 */
function paint() {
  const canvasBaseline = document.getElementById("canvas-baseline");
  const canvasProfile = document.getElementById("canvas-profile");
  if (!canvasBaseline || !canvasProfile) return;

  const skelBaseline = document.getElementById("skel-baseline");
  const onionStack = document.getElementById("onion-stack");
  const wrapperBaseline = stage.mode === "onion"
    ? document.getElementById("onion-viewport")
    : document.getElementById("viewport-baseline");
  const wrapperProfile = stage.mode === "onion" ? wrapperBaseline : document.getElementById("viewport-profile");

  // A failed load leaves img.naturalWidth at 0 -- sizing the pane from that
  // would collapse the canvas to nothing, hiding the "Screenshot not
  // available" message drawScreenshot() already painted onto it at its own
  // fallback size. Skip the explicit sizing pass in that case and let the
  // canvas's own width/height attributes (set by drawScreenshot's onerror
  // branch) stand, same as before zoom/onion sizing existed.
  const revealBaseline = (img) => {
    skelBaseline.hidden = true;
    if (stage.mode === "onion") {
      onionStack.hidden = false;
      if (img.naturalWidth > 0) {
        const { width, height } = paneSize(img, wrapperBaseline);
        onionStack.style.width = `${width}px`;
        onionStack.style.height = `${height}px`;
      }
      wrapperBaseline.classList.toggle("is-zoomed", stage.zoom !== "fit");
    } else {
      canvasBaseline.hidden = false;
      if (img.naturalWidth > 0) sizeCanvas(canvasBaseline, img, wrapperBaseline);
    }
  };
  const revealProfile = (img) => {
    if (stage.mode === "onion") {
      if (img.naturalWidth > 0) {
        const { width, height } = paneSize(img, wrapperBaseline);
        canvasProfile.style.width = `${width}px`;
        canvasProfile.style.height = `${height}px`;
      }
      wireOnionClip();
    } else {
      const skelProfile = document.getElementById("skel-profile");
      skelProfile.hidden = true;
      canvasProfile.hidden = false;
      if (img.naturalWidth > 0) sizeCanvas(canvasProfile, img, wrapperProfile);
    }
  };

  const show = (canvas, key, url, decorate, onLoaded, dimsId) => {
    if (imageIsDrawable(stage[key])) {
      redrawCached(canvas, stage[key], decorate);
      onLoaded(stage[key]);
      return;
    }
    if (stage[key]) return; // in flight or already failed
    stage[key] = drawScreenshot(canvas, url, decorate, (img) => {
      if (img.naturalWidth === 0) {
        const dims = document.getElementById(dimsId);
        if (dims) dims.textContent = "—";
      }
      onLoaded(img);
    });
  };

  show(canvasBaseline, "imgBaseline", imageUrl(stage.dataset, stage.screen, "baseline"),
    decorateBaseline, revealBaseline, "dims-baseline");
  show(canvasProfile, "imgProfile", imageUrl(stage.dataset, stage.screen, stage.profile),
    decorateProfile, revealProfile, "dims-profile");
}

function wireOnionClip() {
  const top = document.getElementById("canvas-profile");
  if (top) top.style.clipPath = `inset(0 ${100 - stage.onionPct}% 0 0)`;
}

// ---------- Selection: target list <-> canvas boxes ----------

function selectTarget(text, { pan = false } = {}) {
  stage.selected = text === stage.selected ? null : text;
  document.querySelectorAll(".stage-target-item").forEach((row) => {
    const active = row.dataset.text === stage.selected;
    row.classList.toggle("is-selected", active);
    row.setAttribute("aria-selected", String(active));
    if (active) row.scrollIntoView({ block: "nearest" });
  });
  paint();
  if (pan && stage.selected) panToTarget(stage.selected);
}

function panToTarget(text) {
  const target = stage.targets.find((t) => t.text === text);
  if (!target?.baseline_box || !imageIsDrawable(stage.imgBaseline)) return;
  const [x1, y1, x2, y2] = target.baseline_box;
  const cx = (x1 + x2) / 2, cy = (y1 + y2) / 2;
  const img = stage.imgBaseline;

  const centerIn = (wrapperId, canvasId) => {
    const wrapper = document.getElementById(wrapperId);
    const canvas = document.getElementById(canvasId);
    if (!wrapper || !canvas || stage.zoom === "fit") return;
    const rect = canvas.getBoundingClientRect();
    const dispX = (cx / img.width) * rect.width;
    const dispY = (cy / img.height) * rect.height;
    wrapper.scrollLeft = Math.max(0, dispX - wrapper.clientWidth / 2);
    wrapper.scrollTop = Math.max(0, dispY - wrapper.clientHeight / 2);
  };

  if (stage.mode === "onion") {
    centerIn("onion-viewport", "canvas-baseline");
  } else {
    centerIn("viewport-baseline", "canvas-baseline");
    centerIn("viewport-profile", "canvas-profile");
  }
}

function handleListKeydown(e) {
  if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
  e.preventDefault();
  const list = orderedTargets();
  if (!list.length) return;
  const idx = list.findIndex((t) => t.text === stage.selected);
  const next = e.key === "ArrowDown"
    ? list[Math.min(list.length - 1, idx + 1)]
    : list[Math.max(0, idx <= 0 ? 0 : idx - 1)];
  selectTarget(next.text, { pan: true });
}

function handleStageKeydown(e) {
  if (e.target.closest("#stage-target-list") || e.target.closest("#onion-divider")) return;
  if (e.key !== "j" && e.key !== "k") return;
  const list = orderedTargets();
  if (!list.length) return;
  const idx = list.findIndex((t) => t.text === stage.selected);
  const next = e.key === "j"
    ? list[Math.min(list.length - 1, idx + 1)]
    : list[Math.max(0, idx <= 0 ? 0 : idx - 1)];
  selectTarget(next.text, { pan: true });
}

window.addEventListener("resize", () => {
  if (document.getElementById("stage-panes")) paint();
});
