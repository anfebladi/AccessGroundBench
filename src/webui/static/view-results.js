"use strict";

/**
 * Results view: one row per result CSV, plus a miss inspector.
 *
 * The status columns keep their CSV names in a tooltip. The human label is
 * what you read; the raw name is what you grep the CSV for, and losing that
 * mapping would make the table harder to act on, not easier.
 */

import { api, enc, imageUrl } from "./api.js";
import {
  badge, cssVar, deltaCell, drawScreenshot, emptyState, html, pct, raw,
  skeleton, stateError, stateLoading, strokeWidthFor,
} from "./ui.js";
import { accuracyChart } from "./charts.js";
import { icon } from "./icons.js";

const STATUS_COLUMNS = [
  ["off_screen", "Off-screen", "Target absent from this profile; never queried."],
  ["label_changed", "Label changed", "Target text renders differently on this profile."],
  ["off_frame", "Off-frame", "Box centre falls outside the cropped image."],
  ["api_error", "API error", "The provider call failed after retries."],
];

let getDataset = () => null;
let rows = [];
let modeFilter = "all";
let sort = { key: "accuracy", dir: "desc" };
// Set true right before the render() that follows a fresh fetch; consumed
// once inside render() so sort/filter clicks (same rows, no new fetch)
// never replay the chart's draw-in animation.
let shouldAnimate = false;
// Keyed by filename (unique per result file, unlike model -- the same model
// can appear once per prompt mode), so a selection made under one mode
// filter survives switching to "All" and back.
let selected = new Set();

export function initResultsView(deps) {
  getDataset = deps.getDataset;
}

export function resultCount() {
  return rows.length;
}

export async function loadResults() {
  const host = document.getElementById("results-body");
  const dataset = getDataset();
  if (!dataset) { host.innerHTML = ""; return; }

  host.innerHTML = skeleton({ rows: 6 });
  try {
    rows = await api(`/api/datasets/${enc(dataset)}/results`);
  } catch (e) {
    rows = [];
    host.innerHTML = stateError(e.message);
    return;
  }
  selected = new Set(rows.map((r) => r.filename).filter((f) => selected.has(f)));
  shouldAnimate = true;
  render();
}

function render() {
  const host = document.getElementById("results-body");
  const filterHost = document.getElementById("results-mode-filter");
  const animate = shouldAnimate;
  shouldAnimate = false;

  if (!rows.length) {
    filterHost.innerHTML = "";
    host.innerHTML = emptyState({
      title: "No evaluations yet",
      body: "Result files appear here once a model has been evaluated against this dataset.",
      action: '<a href="#evaluate"><button type="button">Go to Evaluate</button></a>',
    });
    return;
  }

  const modes = [...new Set(rows.map((r) => r.prompt_mode).filter(Boolean))];
  filterHost.innerHTML = modes.length > 1 ? html`
    <div class="segmented" role="group" aria-label="Prompt mode filter">
      <button type="button" data-mode="all" aria-pressed="${String(modeFilter === "all")}">All</button>
      ${modes.map((m) => raw(html`
        <button type="button" data-mode="${m}" aria-pressed="${String(modeFilter === m)}">${m}</button>`))}
    </div>` : "";
  filterHost.querySelectorAll("button[data-mode]").forEach((btn) => {
    btn.addEventListener("click", () => { modeFilter = btn.dataset.mode; render(); });
  });

  const visible = rows
    .filter((r) => modeFilter === "all" || r.prompt_mode === modeFilter)
    .sort(compare);

  const chartRows = visible
    .filter((r) => r.accuracy !== null)
    .sort((a, b) => b.accuracy - a.accuracy)
    .map((r) => ({ label: r.model, value: r.accuracy }));

  const selectedRows = visible.filter((r) => selected.has(r.filename));

  host.innerHTML = html`
    ${modes.length > 1 ? raw(html`
      <div class="note">
        <span class="note-label">Note</span>
        Vision and tree results answer different research questions and are
        never pooled. Analyze runs one arm at a time.
      </div>`) : ""}
    ${chartRows.length ? raw(html`
      <div class="card">
        <div class="card-head">
          <div>
            <h3>Overall accuracy</h3>
            <p class="card-sub">Blended across every profile, co-present targets only. The exact figures and the baseline-only breakdown are in the table below.</p>
          </div>
          <div class="card-head-actions">
            <button type="button" class="secondary small icon-btn" data-export-chart="results-overall-accuracy"
                    title="Export chart as PNG" aria-label="Export chart as PNG">${raw(icon("download", 14))}</button>
          </div>
        </div>
        <div class="${animate ? "chart-draw-in" : ""}">${raw(accuracyChart(chartRows))}</div>
      </div>`) : ""}
    ${raw(compareSelectedSection(selectedRows))}
    <div class="table-stack">
    <div class="table-wrap">
      <table id="results-table">
        <thead>
          <tr>
            <th class="num" title="Check models to compare them side by side">Compare</th>
            ${raw(th("model", "Model"))}
            ${raw(th("prompt_mode", "Mode"))}
            ${raw(th("row_count", "Rows", "num"))}
            ${raw(th("accuracy", "Accuracy"))}
            <th title="Blended accuracy compared with baseline-only accuracy">vs. baseline</th>
            <th title="Rows excluded from the accuracy denominator, by CSV status">Not scored</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          ${visible.map((r) => raw(renderRow(r)))}
        </tbody>
      </table>
    </div>
    </div>
  `;

  host.querySelectorAll("th.sortable").forEach((el) => {
    el.addEventListener("click", () => {
      const key = el.dataset.sort;
      sort = { key, dir: sort.key === key && sort.dir === "desc" ? "asc" : "desc" };
      render();
    });
  });
  host.querySelectorAll("input[data-compare-select]").forEach((box) => {
    box.addEventListener("change", () => {
      if (box.checked) selected.add(box.dataset.compareSelect);
      else selected.delete(box.dataset.compareSelect);
      render();
    });
  });
  host.querySelector("#results-compare-clear")?.addEventListener("click", () => {
    selected.clear();
    render();
  });
  host.querySelectorAll("button[data-inspect]").forEach((btn) => {
    btn.addEventListener("click", () => openMissInspector(btn.dataset.inspect, btn.dataset.model));
  });
}

function th(key, label, cls = "") {
  return `<th class="${cls} sortable" data-sort="${key}" aria-sort="${ariaSort(key)}">${label}</th>`;
}

function ariaSort(key) {
  if (sort.key !== key) return "none";
  return sort.dir === "asc" ? "ascending" : "descending";
}

function compare(a, b) {
  const dir = sort.dir === "asc" ? 1 : -1;
  const va = sortValue(a, sort.key);
  const vb = sortValue(b, sort.key);
  if (typeof va === "string" || typeof vb === "string") {
    return String(va).localeCompare(String(vb)) * dir;
  }
  return ((va ?? -1) - (vb ?? -1)) * dir;
}

function sortValue(row, key) {
  if (key in row) return row[key];
  return row.statuses[key] || 0;
}

/**
 * Only non-zero statuses are shown. Three of the four are normally zero, and a
 * column of zeros crowded the row without telling anyone anything -- while
 * api_error, the one that means a run is unhealthy, was the easiest to miss.
 */
function notScoredCell(statuses) {
  const parts = STATUS_COLUMNS
    .filter(([key]) => (statuses[key] || 0) > 0)
    .map(([key, label, hint]) => {
      const count = statuses[key];
      if (key === "api_error") return badge("err", `${count} API errors`);
      return html`<span class="tally-item" title="${hint}"><b>${count}</b> ${label}</span>`;
    });
  if (!parts.length) return '<span class="muted">--</span>';
  return `<div class="tally" style="margin-top:0">${parts.join("")}</div>`;
}

function renderRow(r) {
  const accuracy = r.accuracy === null ? null : Number(r.accuracy);
  const accuracyCell = accuracy === null
    ? '<span class="muted">--</span>'
    : html`
      <div class="bar-cell">
        <span class="bar-track"><span class="bar-fill" style="width:${(accuracy * 100).toFixed(1)}%"></span></span>
        <span class="bar-value">${pct(accuracy)}</span>
        <span class="bar-fraction">${r.hits} / ${r.co_present_count}</span>
      </div>`;

  // baseline_accuracy is null when the CSV has no baseline-profile rows at
  // all (e.g. a still-running evaluation); the delta is meaningless without
  // both sides, so it reads as "--" rather than a false zero.
  const baselineAcc = r.baseline_accuracy === null ? null : Number(r.baseline_accuracy);
  const vsBaselineCell = (accuracy === null || baselineAcc === null)
    ? '<span class="muted">--</span>'
    : deltaCell(baselineAcc - accuracy);

  // data-label feeds the stacked-card layout below `md`, where the header row
  // is hidden and each cell has to name itself.
  return html`
    <tr>
      <td class="num" data-label="Compare">
        <input type="checkbox" data-compare-select="${r.filename}" ${raw(selected.has(r.filename) ? "checked" : "")}
               aria-label="Compare ${r.model} (${r.prompt_mode})" />
      </td>
      <td data-label="Model"><b>${r.model}</b></td>
      <td data-label="Mode">${r.prompt_mode || raw('<span class="muted">--</span>')}</td>
      <td class="num" data-label="Rows">${r.row_count}</td>
      <td data-label="Accuracy">${raw(accuracyCell)}</td>
      <td data-label="vs. baseline">${raw(vsBaselineCell)}</td>
      <td data-label="Not scored">${raw(notScoredCell(r.statuses))}</td>
      <td data-label="" style="text-align:right">
        <button type="button" class="secondary small"
                data-inspect="${r.filename}" data-model="${r.model}">Misses</button>
      </td>
    </tr>`;
}

/**
 * A focused view of just the checked models -- reuses accuracyChart (plain
 * accuracy, no inferential statistic computed here) so picking a handful out
 * of a 26-model table doesn't mean scanning the full sorted list for them.
 * Two rows minimum: one checked model has nothing to compare against.
 */
function compareSelectedSection(selectedRows) {
  if (selectedRows.length < 2) return "";
  const chartRows = selectedRows
    .filter((r) => r.accuracy !== null)
    .sort((a, b) => b.accuracy - a.accuracy)
    .map((r) => ({ label: `${r.model}${r.prompt_mode ? ` (${r.prompt_mode})` : ""}`, value: r.accuracy }));

  return html`
    <div class="card card-dark">
      <div class="card-head">
        <div>
          <h3>Comparing ${selectedRows.length} selected models</h3>
          <p class="card-sub">Same accuracy figures as the table below, isolated for a direct look.</p>
        </div>
        <div class="card-head-actions">
          <button type="button" class="secondary small icon-btn" data-export-chart="results-selected-comparison"
                  title="Export chart as PNG" aria-label="Export chart as PNG">${raw(icon("download", 14))}</button>
          <button type="button" class="secondary small" id="results-compare-clear">Clear selection</button>
        </div>
      </div>
      <div class="chart-dark">${raw(accuracyChart(chartRows))}</div>
    </div>`;
}

// ---------- Miss inspector ----------

const inspector = { rows: [], index: 0, model: "", keyHandler: null };

async function openMissInspector(filename, model) {
  const root = document.getElementById("drawer-root");
  root.innerHTML = html`
    <div class="drawer-backdrop">
      <div class="drawer" role="dialog" aria-modal="true" aria-label="Miss inspector">
        <div class="drawer-head"><h3>Misses -- ${model}</h3></div>
        <div class="drawer-body">${raw(stateLoading("Loading rows..."))}</div>
      </div>
    </div>`;

  let allRows;
  try {
    allRows = await api(`/api/datasets/${enc(getDataset())}/results/${enc(filename)}/rows`);
  } catch (e) {
    root.querySelector(".drawer-body").innerHTML = stateError(e.message);
    return;
  }

  inspector.rows = allRows.filter((r) => r.status === "co_present" && r.score === "0");
  inspector.index = 0;
  inspector.model = model;

  inspector.keyHandler = (e) => {
    if (e.key === "Escape") closeInspector();
    if (e.key === "ArrowRight") step(1);
    if (e.key === "ArrowLeft") step(-1);
  };
  document.addEventListener("keydown", inspector.keyHandler);
  root.querySelector(".drawer-backdrop").addEventListener("click", (e) => {
    if (e.target.classList.contains("drawer-backdrop")) closeInspector();
  });

  renderInspector();
}

function closeInspector() {
  if (inspector.keyHandler) document.removeEventListener("keydown", inspector.keyHandler);
  inspector.keyHandler = null;
  document.getElementById("drawer-root").innerHTML = "";
}

function step(delta) {
  if (!inspector.rows.length) return;
  inspector.index = (inspector.index + delta + inspector.rows.length) % inspector.rows.length;
  renderInspector();
}

function renderInspector() {
  const root = document.getElementById("drawer-root");
  const total = inspector.rows.length;

  if (!total) {
    root.innerHTML = html`
      <div class="drawer-backdrop">
        <div class="drawer" role="dialog" aria-modal="true" aria-label="Miss inspector">
          <div class="drawer-head">
            <h3>Misses -- ${inspector.model}</h3>
            <button type="button" class="secondary small" id="drawer-close">Close</button>
          </div>
          <div class="drawer-body">
            ${raw(emptyState({
              title: "No misses to inspect",
              body: "This model scored every co-present target on this dataset.",
            }))}
          </div>
        </div>
      </div>`;
    root.querySelector("#drawer-close").addEventListener("click", closeInspector);
    root.querySelector(".drawer-backdrop").addEventListener("click", (e) => {
      if (e.target.classList.contains("drawer-backdrop")) closeInspector();
    });
    return;
  }

  const row = inspector.rows[inspector.index];
  root.innerHTML = html`
    <div class="drawer-backdrop">
      <div class="drawer" role="dialog" aria-modal="true" aria-label="Miss inspector">
        <div class="drawer-head">
          <h3>Misses -- ${inspector.model}</h3>
          <div class="drawer-nav">
            <span class="drawer-position">${inspector.index + 1} of ${total}</span>
            <button type="button" class="secondary small" data-step="-1" aria-label="Previous miss">Prev</button>
            <button type="button" class="secondary small" data-step="1" aria-label="Next miss">Next</button>
            <button type="button" class="secondary small" id="drawer-close">Close</button>
          </div>
        </div>
        <div class="drawer-body">
          <div class="row">
            <div class="grow">
              <dl class="kv">
                <dt>Target</dt><dd><b>${row.target_text}</b></dd>
                <dt>Screen</dt><dd><code>${row.screen}</code> / <code>${row.profile}</code></dd>
                <dt>Raw reply</dt><dd><code>${row.raw_response || ""}</code></dd>
                <dt>Parsed by</dt><dd>${row.parse_method || "unknown"}</dd>
              </dl>
              <div class="overlay-legend">
                <span class="legend-item" style="color: var(--ok)"><span class="legend-swatch"></span>Ground truth</span>
                <span class="legend-item" style="color: var(--err)"><span class="legend-swatch filled"></span>Predicted point</span>
              </div>
            </div>
            <div>
              <div class="image-frame">
                <canvas id="miss-canvas" style="max-height:56vh; width:auto;"></canvas>
              </div>
            </div>
          </div>
        </div>
        <div class="filmstrip">
          ${inspector.rows.map((r, i) => raw(html`
            <button type="button" data-jump="${i}" aria-current="${String(i === inspector.index)}">${r.target_text}</button>`))}
        </div>
      </div>
    </div>`;

  root.querySelector("#drawer-close").addEventListener("click", closeInspector);
  root.querySelectorAll("button[data-step]").forEach((btn) => {
    btn.addEventListener("click", () => step(Number(btn.dataset.step)));
  });
  root.querySelectorAll("button[data-jump]").forEach((btn) => {
    btn.addEventListener("click", () => { inspector.index = Number(btn.dataset.jump); renderInspector(); });
  });
  root.querySelector(".drawer-backdrop").addEventListener("click", (e) => {
    if (e.target.classList.contains("drawer-backdrop")) closeInspector();
  });
  const current = root.querySelector('button[aria-current="true"]');
  if (current) current.scrollIntoView({ block: "nearest", inline: "center" });

  const ok = cssVar("--ok", "#157a41");
  const err = cssVar("--err", "#b3221a");
  drawScreenshot(
    document.getElementById("miss-canvas"),
    imageUrl(getDataset(), row.screen, row.profile),
    (ctx, img) => {
      ctx.lineWidth = strokeWidthFor(img);
      if (row.x_min !== "" && row.y_min !== "") {
        ctx.strokeStyle = ok;
        ctx.strokeRect(
          Number(row.x_min), Number(row.y_min),
          Number(row.x_max) - Number(row.x_min), Number(row.y_max) - Number(row.y_min)
        );
      }
      if (row.x_pred !== "" && row.y_pred !== "") {
        ctx.fillStyle = err;
        ctx.beginPath();
        ctx.arc(Number(row.x_pred), Number(row.y_pred), Math.max(6, img.width / 80), 0, 2 * Math.PI);
        ctx.fill();
      }
    }
  );
}
