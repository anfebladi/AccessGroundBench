"use strict";

/**
 * Compare view: pick one evaluated model, see baseline versus each
 * accessibility profile immediately -- no analysis run required. This is
 * the benchmark's actual point (CLAUDE.md's headline question: does
 * grounding degrade under an altered layout?), so it gets its own
 * top-level step rather than living inside Results or Analyze.
 *
 * All statistics come from GET .../results/compare, which reuses
 * analysis.reports.grounding.report_per_model -- the exact function
 * `agb analyze` uses for the canonical tables -- so a number shown here can
 * never disagree with what a later analysis run writes to
 * outputs/<dataset>/analysis/. See src/webui/compare.py's module docstring
 * for why the Holm-Bonferroni correction specifically has to run across
 * every model in the dataset, not just the one being displayed.
 */

import { api, enc } from "./api.js";
import {
  badge, deltaCell, escapeHtml, html, raw, stateError, stateLoading,
} from "./ui.js";
import { dumbbellChart, legend } from "./charts.js";
import { icon } from "./icons.js";
import { PROFILES } from "./view-dataset.js";

const PROFILE_LABELS = Object.fromEntries(PROFILES);

let getDataset = () => null;
const state = {
  model: null,
  mode: "vision",
  models: [], // [{model, mode, accuracy}], from /results, deduped by (model, mode)
};

// The last model|mode combination whose chart already played its draw-in
// animation, so re-rendering the same selection doesn't replay it.
let animatedChartKey = null;

export function compareModelCount() {
  return state.models.length;
}

export function initCompareView(deps) {
  getDataset = deps.getDataset;
  document.getElementById("compare-mode-select").addEventListener("change", (e) => {
    state.mode = e.target.value;
    populateModelPicker();
    loadCompare();
  });
  document.getElementById("compare-model-select").addEventListener("change", (e) => {
    state.model = e.target.value || null;
    loadCompare();
  });
}

export async function loadCompareModels() {
  const dataset = getDataset();
  const host = document.getElementById("compare-body");
  if (!dataset) {
    state.models = [];
    populateModelPicker();
    host.innerHTML = "";
    return;
  }
  try {
    state.models = await api(`/api/datasets/${enc(dataset)}/results`);
  } catch (e) {
    state.models = [];
  }
  populateModelPicker();
  await loadCompare();
}

function populateModelPicker() {
  const select = document.getElementById("compare-model-select");
  const forMode = state.models.filter((m) => m.prompt_mode === state.mode);
  if (!forMode.length) {
    select.innerHTML = `<option value="">No ${escapeHtml(state.mode)} results yet</option>`;
    select.disabled = true;
    state.model = null;
    return;
  }
  select.disabled = false;
  const sorted = [...forMode].sort((a, b) =>
    (b.accuracy ?? -1) - (a.accuracy ?? -1));
  select.innerHTML = sorted.map((m) => html`
    <option value="${m.model}">${m.model}${m.accuracy == null ? "" : ` -- ${(m.accuracy * 100).toFixed(1)}% baseline overall`}</option>
  `).join("");
  if (!forMode.some((m) => m.model === state.model)) {
    state.model = sorted[0].model;
  }
  select.value = state.model;
}

async function loadCompare() {
  const host = document.getElementById("compare-body");
  const dataset = getDataset();
  if (!dataset || !state.model) {
    host.innerHTML = "";
    return;
  }

  host.innerHTML = stateLoading("Comparing baseline against each profile...");
  let result;
  try {
    result = await api(
      `/api/datasets/${enc(dataset)}/results/compare`
      + `?model=${enc(state.model)}&mode=${enc(state.mode)}&sample=primary`
    );
  } catch (e) {
    host.innerHTML = raw(stateError(e.message));
    return;
  }

  const rows = result.profiles;
  const chartRows = rows.map((r) => ({
    label: PROFILE_LABELS[r.profile] || r.profile,
    from: r.baseline_accuracy / 100,
    to: r.profile_accuracy / 100,
    underpowered: Boolean(r.power_flag),
  }));

  // Animate only the first time this exact model/mode selection is shown --
  // re-fetching the same selection (e.g. a dataset refresh) does not replay it.
  const chartKey = `${state.model}|${state.mode}`;
  const isFirstRender = animatedChartKey !== chartKey;
  animatedChartKey = chartKey;

  host.innerHTML = html`
    <div class="card card-dark">
      <div class="card-head">
        <div>
          <h3>Baseline versus each profile</h3>
          <p class="card-sub">${result.model} -- ${rows.length} profile${rows.length === 1 ? "" : "s"} tested against baseline, ${result.mode} arm.</p>
        </div>
        <div class="card-head-actions">
          <button type="button" class="secondary small icon-btn" data-export-chart="compare-${result.model}-${result.mode}"
                  title="Export chart as PNG" aria-label="Export chart as PNG">${raw(icon("download", 14))}</button>
        </div>
      </div>
      ${raw(legend([
        { color: "var(--viz-blue)", label: "Baseline accuracy" },
        { color: "var(--viz-orange)", label: "Profile accuracy" },
      ]))}
      <div class="chart-dark${isFirstRender ? " chart-draw-in" : ""}">${raw(dumbbellChart(chartRows))}</div>
    </div>

    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Profile</th>
            <th class="num">Baseline</th>
            <th class="num">Profile</th>
            <th class="num">Delta</th>
            <th class="num">b / c</th>
            <th class="num">Reachable</th>
            <th>Significance</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map((r) => raw(html`
            <tr>
              <td>${PROFILE_LABELS[r.profile] || r.profile}</td>
              <td class="num tabular">${r.baseline_accuracy.toFixed(1)}%</td>
              <td class="num tabular">${r.profile_accuracy.toFixed(1)}%</td>
              <td class="num">${raw(deltaCell(r.delta))}</td>
              <td class="num tabular">${r.b} / ${r.c}</td>
              <td class="num tabular">${r.reachability == null ? "--" : `${(r.reachability * 100).toFixed(1)}%`}</td>
              <td>${raw(significanceBadge(r))}</td>
            </tr>
          `))}
        </tbody>
      </table>
    </div>

    <div class="note">
      <span class="note-label">Note</span>
      Corrected across all ${result.models_in_family.length} model${result.models_in_family.length === 1 ? "" : "s"}
      evaluated on this dataset's ${result.mode} arm (Holm-Bonferroni, &alpha; = 0.05) --
      per-model McNemar is secondary to the pooled permutation test on the Analyze view.
      An underpowered result is not evidence the model is resilient: most of the roster
      sits near ceiling baseline accuracy, where only a handful of discordant pairs are
      possible regardless of the true effect.
    </div>
  `;
}

/**
 * Three states, not two -- see src/webui/compare.py and
 * docs/ui-design-system.md. A plain "not significant" badge on a model at
 * 99% baseline with three discordant pairs would read as "this model is
 * robust," which the data does not support; ceiling/floor rows are flagged
 * as untestable instead of silently rendering the same as a real null.
 */
function significanceBadge(row) {
  if (row.significance_state === "underpowered") {
    return badge("sig-underpowered", `Underpowered -- can't tell (${row.power_flag})`);
  }
  if (row.significance_state === "significant") {
    return badge("sig-yes", "Significant");
  }
  return badge("sig-no", "No significant change");
}
