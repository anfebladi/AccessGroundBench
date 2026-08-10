"use strict";

/**
 * Entry point: dataset selection, hash routing, and the rail status chips.
 *
 * Each view owns its own module and its own fetches; this file only holds what
 * genuinely crosses view boundaries -- which dataset is active, which step is
 * showing, and the one-line status each step reports back to the rail.
 */

import { api } from "./api.js";
import { html } from "./ui.js";
import {
  initDatasetView, loadDataset, selectedScreen,
} from "./view-dataset.js";
import {
  getModels, initModelsView, loadProviders, renderModelList, setSmokeContext,
} from "./view-models.js";
import {
  initEvaluateView, preflightSummary, refreshPreflight, syncModelOptions,
} from "./view-evaluate.js";
import { initResultsView, loadResults, resultCount } from "./view-results.js";
import { initAnalyzeView } from "./view-analyze.js";
import { initCollectView } from "./view-collect.js";

const TABS = ["dataset", "models", "evaluate", "collect", "results", "analyze"];

const state = {
  datasets: [],
  dataset: null,
  providers: [],
};

const getDataset = () => state.dataset;

// ---------- Routing ----------

function showTab(name) {
  const tab = TABS.includes(name) ? name : "dataset";
  for (const id of TABS) {
    document.getElementById(`tab-${id}`).hidden = id !== tab;
  }
  document.querySelectorAll("#rail a").forEach((link) => {
    if (link.dataset.tab === tab) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  window.scrollTo({ top: 0 });
}

window.addEventListener("hashchange", () => showTab((location.hash || "#dataset").slice(1)));

// ---------- Rail status ----------

function setChip(tab, text, tone = "") {
  const chip = document.querySelector(`.rail-chip[data-chip="${tab}"]`);
  if (!chip) return;
  chip.textContent = text || "";
  chip.className = `rail-chip${tone ? ` is-${tone}` : ""}`;
}

function refreshChips() {
  const info = state.datasets.find((d) => d.name === state.dataset);
  if (info) {
    setChip("dataset", info.is_archived
      ? "archived, read-only"
      : `${info.screen_count} screens`, info.is_archived ? "warn" : "");
  } else {
    setChip("dataset", "");
  }

  const models = getModels();
  const configured = state.providers.filter((p) => p.configured).length;
  setChip("models", models.length
    ? `${models.length} model${models.length === 1 ? "" : "s"}, ${configured} provider${configured === 1 ? "" : "s"}`
    : "none configured", models.length ? "" : "warn");

  setChip("evaluate", preflightSummary());

  const count = resultCount();
  setChip("results", count ? `${count} result file${count === 1 ? "" : "s"}` : "no runs yet");
  setChip("analyze", count ? "" : "needs results");
}

// ---------- Dataset selection ----------

async function loadDatasets() {
  const select = document.getElementById("dataset-select");
  state.datasets = await api("/api/datasets");

  select.innerHTML = state.datasets.map((d) => html`
    <option value="${d.name}">${d.is_archived ? `${d.name} (archived)` : d.name}</option>
  `).join("");

  if (state.datasets.length) {
    // Keep the current selection across a reload triggered by a finished run.
    if (!state.datasets.some((d) => d.name === state.dataset)) {
      state.dataset = state.datasets[0].name;
    }
    select.value = state.dataset;
  } else {
    state.dataset = null;
  }

  select.onchange = () => {
    state.dataset = select.value;
    onDatasetChanged();
  };
  await onDatasetChanged();
}

async function onDatasetChanged() {
  const info = state.datasets.find((d) => d.name === state.dataset);
  document.getElementById("dataset-meta").textContent = info
    ? `${info.screen_count} screens, ${info.image_count} images`
      + (info.is_archived ? " -- archived, read-only" : "")
    : "";

  await loadDataset(state.dataset);
  await Promise.all([loadResults(), refreshPreflight()]);
  refreshChips();
}

// ---------- Init ----------

async function init() {
  showTab((location.hash || "#dataset").slice(1));

  initDatasetView(getDataset);
  setSmokeContext(getDataset, selectedScreen);
  initResultsView({ getDataset });
  initAnalyzeView({ getDataset });
  initEvaluateView({
    getDataset,
    getModels,
    onRunFinished: async () => {
      await loadResults();
      refreshChips();
    },
  });
  initCollectView({
    onRunFinished: async () => {
      await loadDatasets();
    },
  });
  initModelsView({
    onChange: () => {
      syncModelOptions();
      refreshChips();
    },
  });

  await loadDatasets();
  try {
    state.providers = await api("/api/providers");
  } catch (e) {
    state.providers = [];
  }
  await loadProviders();
  renderModelList();
  refreshChips();
}

init();
