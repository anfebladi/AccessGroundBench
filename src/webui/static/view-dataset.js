"use strict";

/**
 * Dataset view: capture warnings, and a baseline-vs-profile comparison.
 *
 * The comparison is the point of the view. This benchmark's headline finding is
 * that heavy accessibility profiles evict targets from the screen entirely, and
 * a single-image browser cannot show that -- you have to see which baseline
 * targets are gone, side by side, at the same display height.
 */

import { api, enc } from "./api.js";
import { badge, emptyState, html, raw, stateError, stateLoading } from "./ui.js";
import { PROFILES, renderComparisonStage, renderEmptyStage } from "./compare-stage.js";

export { PROFILES };

const state = {
  screens: [],
  filter: "",
  selected: null,
  profile: "elder_combo_max",
};

// Bumped on every renderBrowser() call so a slower, older fetch can tell it
// has been superseded by a newer screen/profile pick and bail out instead of
// overwriting the panel with stale data that arrived late.
let renderToken = 0;

export function selectedScreen() {
  return state.selected;
}

/** Every screen name in the currently loaded dataset, for the command palette. */
export function screenList() {
  return state.screens;
}

export async function loadDataset(dataset) {
  state.selected = null;
  await Promise.all([loadScreens(dataset), loadWarnings(dataset)]);
  renderBrowser(dataset);
}

/** Jump straight to a screen -- the command palette's route into this view. */
export async function selectScreen(dataset, screen) {
  if (!state.screens.includes(screen) || state.selected === screen) return;
  state.selected = screen;
  renderScreenList(dataset);
  await renderBrowser(dataset);
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
      <div class="note note-warn">
        <span class="note-label">Warning</span>
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
        <div class="note note-warn">
          <span class="note-label">Warning</span>
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
//
// All rendering and interaction for the comparison itself -- panes, zoom/pan,
// onion-skin, the target list, keyboard stepping -- lives in compare-stage.js.
// This view's job stops at resolving a screen/profile pick into targets and
// profile labels and handing them over.

async function renderBrowser(dataset) {
  const token = ++renderToken;

  if (!dataset || !state.selected) {
    renderEmptyStage(emptyState({
      title: "No screen selected",
      body: "Pick a screen from the list to compare its baseline capture against an accessibility profile.",
    }));
    return;
  }

  const screen = state.selected;
  const container = document.getElementById("screen-browser");

  // Switching screen or profile keeps the current screenshots on screen,
  // just dimmed, while the next ones load -- blanking the whole panel to a
  // bare "Loading..." line on every click is what read as a glitch. The
  // first-ever load has nothing to keep visible, so it still shows the
  // loading state outright.
  if (container.querySelector(".stage-body")) {
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
    container.classList.remove("is-loading");
    renderEmptyStage(stateError(e.message));
    return;
  }

  // Reachability, computed the same way the analysis does it: a baseline
  // target survives if its exact text still renders somewhere on the profile.
  const profileTexts = new Set(
    profileLabels.map((r) => (r.text || "").trim()).filter(Boolean)
  );
  const present = targets.filter((t) => profileTexts.has(t.text));
  const missing = targets.filter((t) => !profileTexts.has(t.text));
  const profileLabel = PROFILES.find(([id]) => id === state.profile)?.[1] || state.profile;
  const isBaselineBoth = state.profile === "baseline";

  container.classList.remove("is-loading");
  renderComparisonStage(dataset, screen, {
    profile: state.profile, profileLabel, isBaselineBoth,
    targets, present, missing, profileLabels,
  }, (profile) => {
    state.profile = profile;
    renderBrowser(dataset);
  });
}
