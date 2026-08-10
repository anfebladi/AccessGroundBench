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
      state.selected = li.dataset.screen;
      renderScreenList(dataset);
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

function renderOverlayToggles(dataset) {
  const host = document.getElementById("compare-overlay-toggles");
  host.innerHTML = html`
    <div class="segmented">
      <button type="button" data-toggle="showBoxes" aria-pressed="${String(state.showBoxes)}">Target boxes</button>
      <button type="button" data-toggle="showMissing" aria-pressed="${String(state.showMissing)}">Missing targets</button>
    </div>
  `;
  host.querySelectorAll("button[data-toggle]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const key = btn.dataset.toggle;
      state[key] = !state[key];
      renderOverlayToggles(dataset);
      renderBrowser(dataset);
    });
  });
}

async function renderBrowser(dataset) {
  const container = document.getElementById("screen-browser");
  renderOverlayToggles(dataset);

  if (!dataset || !state.selected) {
    container.innerHTML = emptyState({
      title: "No screen selected",
      body: "Pick a screen from the list to compare its baseline capture against an accessibility profile.",
    });
    return;
  }

  const screen = state.selected;
  container.innerHTML = stateLoading("Loading captures...");

  let targets = [];
  let profileLabels = [];
  try {
    const [targetsRes, labelsRes] = await Promise.all([
      api(`/api/datasets/${enc(dataset)}/targets/${enc(screen)}`),
      api(`/api/datasets/${enc(dataset)}/labels/${enc(screen)}/${enc(state.profile)}`).catch(() => []),
    ]);
    targets = targetsRes.targets || [];
    profileLabels = labelsRes || [];
  } catch (e) {
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

  const accent = cssVar("--viz-blue", "#2a78d6");
  const err = cssVar("--err", "#b3221a");

  drawScreenshot(
    document.getElementById("canvas-baseline"),
    imageUrl(dataset, screen, "baseline"),
    (ctx, img) => {
      document.getElementById("dims-baseline").textContent = `${img.width} x ${img.height}`;
      ctx.lineWidth = strokeWidthFor(img);
      if (state.showBoxes) {
        ctx.strokeStyle = accent;
        for (const t of present) strokeBox(ctx, t.baseline_box);
      }
      if (state.showMissing && !isBaselineBoth) {
        ctx.strokeStyle = err;
        for (const t of missing) strokeBox(ctx, t.baseline_box);
      }
    }
  );

  drawScreenshot(
    document.getElementById("canvas-profile"),
    imageUrl(dataset, screen, state.profile),
    (ctx, img) => {
      // Dimensions differ from baseline whenever density changes -- surfacing
      // that is the point, since label coordinates are not comparable across
      // profiles without accounting for it.
      document.getElementById("dims-profile").textContent = `${img.width} x ${img.height}`;
      if (!state.showBoxes) return;
      ctx.lineWidth = strokeWidthFor(img);
      ctx.strokeStyle = accent;
      const wanted = new Set(present.map((t) => t.text));
      for (const rec of profileLabels) {
        if (rec.box && wanted.has((rec.text || "").trim())) strokeBox(ctx, rec.box);
      }
    }
  );
}

function strokeBox(ctx, box) {
  if (!box) return;
  const [x1, y1, x2, y2] = box;
  ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
}
