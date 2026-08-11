"use strict";

/**
 * Dataset view: capture warnings, and a baseline-vs-profile comparison.
 *
 * The comparison is the point of the view. This benchmark's headline finding is
 * that heavy accessibility profiles evict targets from the screen entirely, and
 * a single-image browser cannot show that -- you have to see which baseline
 * targets are gone, side by side, at the same display height.
 */

import { api, enc, imageUrl } from "./api.js";
import {
  badge, cssVar, drawScreenshot, emptyState, html,
  pct, raw, stateError, stateLoading, strokeWidthFor,
} from "./ui.js";

export const PROFILES = [
  ["baseline", "Baseline"],
  ["elder_text_heavy", "Text heavy"],
  ["elder_zoom_heavy", "Zoom heavy"],
  ["elder_combo_mid", "Combo mid"],
  ["elder_combo_max", "Combo max"],
  ["colorblind_deuteranomaly", "Deuteranomaly"],
];

const state = {
  screens: [],
  filter: "",
  selected: null,
  profile: "elder_combo_max",
  showBoxes: true,
  showMissing: true,
};

// Last-loaded comparison data, kept so the overlay toggles can redraw the
// two canvases in place -- no re-fetch, no rebuilding the panes -- instead
// of running the full fetch-and-rebuild path a screen/profile change needs.
let lastComparison = null;

// Bumped on every renderBrowser() call so a slower, older fetch can tell it
// has been superseded by a newer screen/profile pick and bail out instead of
// overwriting the panel with stale data that arrived late.
let renderToken = 0;

export function selectedScreen() {
  return state.selected;
}

export async function loadDataset(dataset) {
  state.selected = null;
  await Promise.all([loadScreens(dataset), loadWarnings(dataset)]);
  renderBrowser(dataset);
}

// ---------- Capture warnings ----------

async function loadWarnings(dataset) {
  const container = document.getElementById("dataset-warnings");
  if (!dataset) { container.innerHTML = ""; return; }

  let data;
  try {
    data = await api(`/api/datasets/${enc(dataset)}/manifest`);
  } catch (e) {
    container.innerHTML = "";
    return;
  }

  if (!data.available) {
    container.innerHTML = html`
      <div class="note">
        No <code>collection_manifest.json</code> for this dataset, so capture
        completeness and content drift are unknown.
      </div>`;
    return;
  }

  const m = data.manifest;
  const complete = m.expected_captures === m.successful_captures;
  const problems = m.problems || [];

  container.innerHTML = html`
    <div class="card">
      <div class="card-head">
        <div>
          <h3>Capture health</h3>
          <p class="card-sub">Read this before trusting any number reported against this dataset.</p>
        </div>
        <div class="card-head-actions">
          ${raw(complete
            ? badge("ok", `${m.successful_captures}/${m.expected_captures} captures complete`)
            : badge("err", `${m.successful_captures}/${m.expected_captures} captures -- incomplete`))}
        </div>
      </div>
      ${problems.length ? raw(html`
        <div class="note">
          <b>${problems.length} warning${problems.length === 1 ? "" : "s"}</b> --
          affected screens carry a caveat, they are not automatically excluded.
          <ul>${problems.map((p) => raw(html`<li>${p}</li>`))}</ul>
        </div>`) : raw('<p class="muted small">No drift or contamination warnings recorded.</p>')}
    </div>
  `;
}

// ---------- Screen picker ----------

async function loadScreens(dataset) {
  const list = document.getElementById("screen-list");
  if (!dataset) { state.screens = []; list.innerHTML = ""; return; }
  const { screens } = await api(`/api/datasets/${enc(dataset)}/screens`);
  state.screens = screens;
  state.selected = screens[0] || null;
  renderScreenList(dataset);
}

function renderScreenList(dataset) {
  const list = document.getElementById("screen-list");
  const visible = state.screens.filter((s) => s.includes(state.filter));
  if (!visible.length) {
    list.innerHTML = html`<li class="muted" style="cursor:default">No matching screens</li>`;
    return;
  }
  list.innerHTML = visible.map((s) => html`
    <li data-screen="${s}" class="${raw(s === state.selected ? "selected" : "")}">${s}</li>
  `).join("");
  list.querySelectorAll("li[data-screen]").forEach((li) => {
    li.addEventListener("click", () => {
      if (li.dataset.screen === state.selected) return;
      // Move the .selected class directly rather than rebuilding the whole
      // list -- picking a screen shouldn't tear down and recreate every
      // other row's DOM node and click listener.
      list.querySelector("li.selected")?.classList.remove("selected");
      li.classList.add("selected");
      state.selected = li.dataset.screen;
      renderBrowser(dataset);
    });
  });
}

export function initDatasetView(getDataset) {
  document.getElementById("screen-filter").addEventListener("input", (e) => {
    state.filter = e.target.value.trim().toLowerCase();
    renderScreenList(getDataset());
  });
}

// ---------- Comparison ----------

// Real checkboxes, not segmented-tab buttons: unlike the profile picker
// below (a single-select group -- exactly one profile is ever active),
// these two are independent on/off overlays that can be any combination of
// checked. Styling them like the exclusive-choice segmented control implied
// "pick one of these," which is the wrong affordance for what they do.
function renderOverlayToggles(dataset) {
  const host = document.getElementById("compare-overlay-toggles");
  host.innerHTML = html`
    <label class="chip-check">
      <input type="checkbox" data-toggle="showBoxes" ${raw(state.showBoxes ? "checked" : "")} />
      Target boxes
    </label>
    <label class="chip-check">
      <input type="checkbox" data-toggle="showMissing" ${raw(state.showMissing ? "checked" : "")} />
      Missing targets
    </label>
  `;
  host.querySelectorAll("input[data-toggle]").forEach((box) => {
    box.addEventListener("change", () => {
      state[box.dataset.toggle] = box.checked;
      redrawOverlays();
    });
  });
}

async function renderBrowser(dataset) {
  const container = document.getElementById("screen-browser");
  renderOverlayToggles(dataset);
  const token = ++renderToken;

  if (!dataset || !state.selected) {
    lastComparison = null;
    container.classList.remove("is-loading");
    container.innerHTML = emptyState({
      title: "No screen selected",
      body: "Pick a screen from the list to compare its baseline capture against an accessibility profile.",
    });
    return;
  }

  const screen = state.selected;

  // Switching screen or profile keeps the current screenshots on screen,
  // just dimmed, while the next ones load -- blanking the whole panel to a
  // bare "Loading..." line on every click is what read as a glitch. The
  // first-ever load has nothing to keep visible, so it still shows the
  // loading state outright.
  if (container.querySelector(".compare")) {
    container.classList.add("is-loading");
  } else {
    container.innerHTML = stateLoading("Loading captures...");
  }

  let targets = [];
  let profileLabels = [];
  try {
    const [targetsRes, labelsRes] = await Promise.all([
      api(`/api/datasets/${enc(dataset)}/targets/${enc(screen)}`),
      api(`/api/datasets/${enc(dataset)}/labels/${enc(screen)}/${enc(state.profile)}`).catch(() => []),
    ]);
    if (token !== renderToken) return; // a newer pick has already superseded this fetch
    targets = targetsRes.targets || [];
    profileLabels = labelsRes || [];
  } catch (e) {
    if (token !== renderToken) return;
    lastComparison = null;
    container.classList.remove("is-loading");
    container.innerHTML = stateError(e.message);
    return;
  }

  // Reachability, computed the same way the analysis does it: a baseline
  // target survives if its exact text still renders somewhere on the profile.
  const profileTexts = new Set(
    profileLabels.map((r) => (r.text || "").trim()).filter(Boolean)
  );
  const present = targets.filter((t) => profileTexts.has(t.text));
  const missing = targets.filter((t) => !profileTexts.has(t.text));
  const reachability = targets.length ? present.length / targets.length : null;

  const profileLabel = PROFILES.find(([id]) => id === state.profile)?.[1] || state.profile;
  const isBaselineBoth = state.profile === "baseline";
  const profileCaption = isBaselineBoth
    ? "Same capture as the left pane."
    : `${present.length} of ${targets.length} baseline targets still present`
      + (reachability === null ? "" : ` (${pct(reachability)} reachable)`);

  container.classList.remove("is-loading");
  container.innerHTML = html`
    <div class="segmented" id="profile-picker" role="group" aria-label="Accessibility profile">
      ${PROFILES.map(([id, label]) => raw(html`
        <button type="button" data-profile="${id}" aria-pressed="${String(id === state.profile)}">${label}</button>
      `))}
    </div>

    <div class="compare" style="margin-top: var(--space-4);">
      <div class="pane">
        <div class="pane-head">
          <span class="pane-title">Baseline</span>
          <span class="pane-dims" id="dims-baseline"></span>
        </div>
        <div class="pane-canvas"><canvas id="canvas-baseline"></canvas></div>
        <p class="image-caption">${targets.length} groundable target${targets.length === 1 ? "" : "s"}</p>
      </div>
      <div class="pane">
        <div class="pane-head">
          <span class="pane-title">${profileLabel}</span>
          <span class="pane-dims" id="dims-profile"></span>
        </div>
        <div class="pane-canvas"><canvas id="canvas-profile"></canvas></div>
        <p class="image-caption">${profileCaption}</p>
      </div>
    </div>

    ${!isBaselineBoth && missing.length ? raw(html`
      <div class="note" style="margin-top: var(--space-4);">
        <b>${missing.length} target${missing.length === 1 ? "" : "s"} evicted by this profile.</b>
        They are outlined on the baseline pane. A target that no longer renders
        cannot be grounded by any model, so it is scored as
        <code>off_screen</code> rather than as a miss.
        <div class="small muted" style="margin-top: var(--space-2);">
          ${missing.slice(0, 8).map((t) => raw(html`<code>${t.text}</code> `))}
          ${missing.length > 8 ? raw(html`<span>and ${missing.length - 8} more</span>`) : ""}
        </div>
      </div>`) : ""}

    <div class="overlay-legend" style="margin-top: var(--space-4);">
      <span class="legend-item" style="color: var(--viz-blue)"><span class="legend-swatch"></span>Groundable target</span>
      <span class="legend-item" style="color: var(--err)"><span class="legend-swatch"></span>Missing from this profile</span>
    </div>
  `;

  container.querySelectorAll("button[data-profile]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.profile = btn.dataset.profile;
      renderBrowser(dataset);
    });
  });

  lastComparison = {
    dataset, screen, profile: state.profile,
    present, missing, profileLabels, isBaselineBoth,
  };
  redrawOverlays();
}

/**
 * Redraw the two canvases from the last-fetched comparison data, honouring
 * the current showBoxes/showMissing toggle state. No network call and no
 * touching the surrounding panes -- this is what the overlay toggle buttons
 * call, so ticking "Target boxes" on or off is an instant local redraw, not
 * a full reload of the comparison panel.
 *
 * The screenshot images are cached on `lastComparison` after their first
 * load and redrawn from that cache here. `imageUrl()` appends a cache-busting
 * timestamp (so a re-collected capture is never served stale), which also
 * means a naive re-fetch would hit the network for the same pixels on every
 * toggle click -- a visible flash for zero new information.
 */
function redrawOverlays() {
  if (!lastComparison) return;
  const c = lastComparison;
  const canvasBaseline = document.getElementById("canvas-baseline");
  const canvasProfile = document.getElementById("canvas-profile");
  if (!canvasBaseline || !canvasProfile) return;

  const accent = cssVar("--viz-blue", "#2a78d6");
  const err = cssVar("--err", "#b3221a");

  const decorateBaseline = (ctx, img) => {
    document.getElementById("dims-baseline").textContent = `${img.width} x ${img.height}`;
    ctx.lineWidth = strokeWidthFor(img);
    if (state.showBoxes) {
      ctx.strokeStyle = accent;
      for (const t of c.present) strokeBox(ctx, t.baseline_box);
    }
    if (state.showMissing && !c.isBaselineBoth) {
      ctx.strokeStyle = err;
      for (const t of c.missing) strokeBox(ctx, t.baseline_box);
    }
  };

  const decorateProfile = (ctx, img) => {
    // Dimensions differ from baseline whenever density changes -- surfacing
    // that is the point, since label coordinates are not comparable across
    // profiles without accounting for it.
    document.getElementById("dims-profile").textContent = `${img.width} x ${img.height}`;
    if (!state.showBoxes) return;
    ctx.lineWidth = strokeWidthFor(img);
    ctx.strokeStyle = accent;
    const wanted = new Set(c.present.map((t) => t.text));
    for (const rec of c.profileLabels) {
      if (rec.box && wanted.has((rec.text || "").trim())) strokeBox(ctx, rec.box);
    }
  };

  if (c.imgBaseline?.complete) {
    redrawCached(canvasBaseline, c.imgBaseline, decorateBaseline);
  } else {
    c.imgBaseline = drawScreenshot(canvasBaseline, imageUrl(c.dataset, c.screen, "baseline"), decorateBaseline);
  }

  if (c.imgProfile?.complete) {
    redrawCached(canvasProfile, c.imgProfile, decorateProfile);
  } else {
    c.imgProfile = drawScreenshot(canvasProfile, imageUrl(c.dataset, c.screen, c.profile), decorateProfile);
  }
}

function redrawCached(canvas, img, decorate) {
  const ctx = canvas.getContext("2d");
  canvas.width = img.width;
  canvas.height = img.height;
  ctx.drawImage(img, 0, 0);
  decorate(ctx, img);
}

function strokeBox(ctx, box) {
  if (!box) return;
  const [x1, y1, x2, y2] = box;
  ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
}
