"use strict";

/**
 * Analyze view.
 *
 * The charts are the scan layer; the tables underneath them stay the source of
 * truth and are one disclosure away. The methodological caveats -- pooled test
 * primary, per-model McNemar secondary, an underpowered null is not evidence of
 * resilience, and the co-present set is not profile-independent -- are part of
 * the output, not decoration, and are rendered whether or not anyone opens a
 * table.
 */

import { api } from "./api.js";
import { badge, escapeHtml, html, raw, setLoading, stateError } from "./ui.js";
import {
  directionChart, discordantChart, dumbbellChart, legend, reachabilityChart,
} from "./charts.js";

let getDataset = () => null;
let lastResult = null;
let dumbbellProfile = null;

export function initAnalyzeView(deps) {
  getDataset = deps.getDataset;
  document.getElementById("analyze-form").addEventListener("submit", runAnalysis);
}

async function runAnalysis(e) {
  e.preventDefault();
  const out = document.getElementById("analyze-results");
  const submit = document.getElementById("analyze-submit");
  const permutations = Number(document.getElementById("analyze-permutations").value) || 20000;

  const payload = {
    dataset: getDataset(),
    sample: document.getElementById("analyze-sample").value,
    mode: document.getElementById("analyze-mode").value,
    permutations,
    seed: Number(document.getElementById("analyze-seed").value) || 0,
  };

  // The endpoint runs the analysis in-process and blocks until it finishes, so
  // the form is locked for the duration rather than left looking clickable.
  const stopLoading = setLoading(submit, true, "Running");
  out.innerHTML = html`
    <div class="card">
      <p class="state-loading">Running ${permutations.toLocaleString()} permutations. This can take a minute.</p>
      <div class="progress is-indeterminate" style="margin-top: var(--space-3);"><div class="progress-fill"></div></div>
    </div>`;

  try {
    lastResult = await api("/api/analyze", { method: "POST", body: JSON.stringify(payload) });
  } catch (err) {
    lastResult = null;
    out.innerHTML = html`<div class="card">${raw(stateError(err.message))}</div>`;
    return;
  } finally {
    stopLoading();
  }

  dumbbellProfile = null;
  render();
}

function render() {
  const out = document.getElementById("analyze-results");
  const r = lastResult;
  if (!r) return;

  out.innerHTML = `
    ${caveats()}
    ${writtenTo(r.output_dir)}
    ${reachabilitySection(r.reachability || [])}
    ${pooledSection(r.pooled_permutation || [])}
    ${perModelSection(r.mcnemar_per_model || [])}
    ${directionSection(r.direction_consistency || [])}
  `;

  out.querySelectorAll("button[data-dumbbell-profile]").forEach((btn) => {
    btn.addEventListener("click", () => {
      dumbbellProfile = btn.dataset.dumbbellProfile;
      render();
      document.getElementById("per-model-card").scrollIntoView({ block: "nearest" });
    });
  });
}

/**
 * Where the tables landed. Worth saying out loud: a reader who knows
 * `agb analyze` will expect them in the dataset directory, and the whole point
 * of writing them elsewhere is that the dataset's own tables stay untouched.
 */
function writtenTo(dir) {
  if (!dir) return "";
  return html`
    <p class="muted small" style="margin: 0 0 var(--space-4);">
      Tables written to <code>${dir}/</code> -- the dataset's own analysis files are left alone.
    </p>`;
}

function caveats() {
  return `
    <div class="note note-info">
      <b>Pooled permutation is the primary test; per-model McNemar is secondary.</b>
      Rows flagged ceiling or floor are underpowered, and an underpowered null is
      not evidence that a model is resilient. Reachability carries a survivorship
      caveat on the heaviest profiles: the co-present set is not
      profile-independent, so baseline accuracy measured only over the targets
      that survived a hard profile reads higher than the model's true baseline.
      See <code>docs/methods.md</code>.
    </div>`;
}

// ---------- Reachability ----------

function reachabilitySection(rows) {
  if (!rows.length) return emptyCard("Reachability", "No reachability rows were produced.");
  const chartRows = rows.map((r) => ({
    label: r.Profile,
    value: frac(r.Reachability),
    lo: frac(r.CI_Low),
    hi: frac(r.CI_High),
  }));

  const table = dataTable(
    ["Sample", "Profile", "Present / total", "Reachability", "95% CI"],
    rows.map((r) => [
      r.Sample, r.Profile, `${r.Targets_Present}/${r.Targets_Total}`,
      fmtPct(r.Reachability), `[${fmtPct(r.CI_Low)}, ${fmtPct(r.CI_High)}]`,
    ])
  );

  return card("Reachability",
    "Share of baseline targets that still render under each profile. A target that is gone cannot be grounded by any model.",
    reachabilityChart(chartRows) + table);
}

// ---------- Pooled permutation ----------

function pooledSection(rows) {
  if (!rows.length) return emptyCard("Pooled permutation", "No pooled rows were produced.");

  const chartRows = rows.map((r) => ({
    label: r.Profile,
    left: Number(r.Broke_It_b),
    right: Number(r.Fluke_Recovery_c),
    significant: r.Significant === "Yes",
    annotation: `p = ${Number(r.P_Value).toFixed(4)}`,
  }));

  const key = legend([
    { color: "var(--viz-red)", label: "Broke it (b)" },
    { color: "var(--viz-blue)", label: "Recovered (c)" },
    { color: "var(--text)", label: "Filled square: significant after Holm" },
    { color: "var(--text-2)", label: "Hollow square: not significant", shape: "hollow" },
  ]);

  const table = dataTable(
    ["Sample", "Profile", "Broke it (b)", "Recovered (c)", "p", "Holm-significant"],
    rows.map((r) => [
      r.Sample, r.Profile, r.Broke_It_b, r.Fluke_Recovery_c,
      Number(r.P_Value).toFixed(4),
      markup(r.Significant === "Yes" ? badge("ok", "significant") : badge("muted", "ns")),
    ])
  );

  return card("Pooled permutation (primary)",
    "Cluster permutation across models, clustered on target. Discordant pairs only.",
    key + discordantChart(chartRows) + table);
}

// ---------- Per-model McNemar ----------

function perModelSection(rows) {
  if (!rows.length) return emptyCard("Per-model McNemar", "No per-model rows were produced.");

  const profiles = [...new Set(rows.map((r) => r.Profile))];
  const active = dumbbellProfile && profiles.includes(dumbbellProfile) ? dumbbellProfile : profiles[0];
  const visible = rows.filter((r) => r.Profile === active);

  const chartRows = visible.map((r) => ({
    label: r.Model,
    from: frac(r.Baseline_Acc),
    to: frac(r.Exp_Acc),
    underpowered: isUnderpowered(r.Power_Limit),
  }));

  const picker = `
    <div class="segmented" role="group" aria-label="Profile">
      ${profiles.map((p) => `
        <button type="button" data-dumbbell-profile="${escapeHtml(p)}"
                aria-pressed="${String(p === active)}">${escapeHtml(p)}</button>`).join("")}
    </div>`;

  const key = legend([
    { color: "var(--viz-blue)", label: "Baseline accuracy" },
    { color: "var(--viz-orange)", label: "Accuracy under this profile" },
    { color: "var(--text-2)", label: "† underpowered (ceiling or floor)" },
  ]);

  const table = dataTable(
    ["Sample", "Model", "Profile", "Baseline", "Profile acc", "p", "Power"],
    rows.map((r) => [
      r.Sample, r.Model, r.Profile, fmtPct(r.Baseline_Acc), fmtPct(r.Exp_Acc),
      Number(r.P_Value).toFixed(4),
      markup(isUnderpowered(r.Power_Limit)
        ? badge("warn", `${r.Power_Limit} -- underpowered, not evidence of resilience`)
        : ""),
    ])
  );

  return `
    <div class="card" id="per-model-card">
      <div class="card-head">
        <div>
          <h3>Per-model McNemar (secondary)</h3>
          <p class="card-sub">Co-present targets only, Holm-corrected across the family.</p>
        </div>
        <div class="card-head-actions">${picker}</div>
      </div>
      ${key}
      ${dumbbellChart(chartRows)}
      ${table}
    </div>`;
}

function isUnderpowered(flag) {
  return Boolean(flag) && flag !== "-" && flag.toLowerCase() !== "none";
}

// ---------- Direction consistency ----------

function directionSection(rows) {
  if (!rows.length) return emptyCard("Direction consistency", "No sign-test rows were produced.");

  const chartRows = rows.map((r) => ({
    label: r.Profile,
    down: Number(r.Models_Down),
    up: Number(r.Models_Up),
    tied: Number(r.Models_Tied),
    p: Number(r.Sign_P_Value).toFixed(4),
  }));

  const key = legend([
    { color: "var(--viz-red)", label: "Accuracy down" },
    { color: "var(--viz-neutral)", label: "Tied" },
    { color: "var(--viz-blue)", label: "Accuracy up" },
  ]);

  const table = dataTable(
    ["Sample", "Profile", "Down", "Up", "Tied", "Sign p"],
    rows.map((r) => [r.Sample, r.Profile, r.Models_Down, r.Models_Up, r.Models_Tied,
      Number(r.Sign_P_Value).toFixed(4)])
  );

  return card("Direction consistency (descriptive)",
    "Counts models by direction of change. Result CSVs are not independent models -- configuration variants of one base model share a row here.",
    key + directionChart(chartRows) + table);
}

// ---------- Shared shells ----------

function card(title, subtitle, body) {
  return `
    <div class="card">
      <div class="card-head">
        <div>
          <h3>${title}</h3>
          <p class="card-sub">${subtitle}</p>
        </div>
      </div>
      ${body}
    </div>`;
}

function emptyCard(title, message) {
  return `<div class="card"><h3>${title}</h3><p class="muted small">${message}</p></div>`;
}

/**
 * Cells are escaped unless wrapped in markup() -- model names reach these
 * tables from user-supplied model ids by way of the result filename, so plain
 * values are never trusted.
 */
function markup(value) {
  return { __html: value };
}

function dataTable(headers, rows) {
  const cell = (c) => {
    if (c === null || c === undefined) return "";
    return typeof c === "object" && "__html" in c ? c.__html : escapeHtml(c);
  };
  return `
    <details class="data-table">
      <summary>Show table</summary>
      <div class="table-wrap">
        <table>
          <thead><tr>${headers.map((h) => `<th>${escapeHtml(h)}</th>`).join("")}</tr></thead>
          <tbody>
            ${rows.map((cells) => `<tr>${cells.map((c) => `<td>${cell(c)}</td>`).join("")}</tr>`).join("")}
          </tbody>
        </table>
      </div>
    </details>`;
}

/**
 * Analysis CSVs are not uniform: reachability writes a bare fraction
 * (`0.903`) while the per-model McNemar table writes an already-formatted
 * percent string (`"96.4%"`). Both reach the charts, so both are normalised to
 * a fraction here rather than trusting Number() to cope.
 */
function frac(value) {
  if (typeof value === "string" && value.trim().endsWith("%")) {
    const n = Number(value.trim().slice(0, -1));
    return Number.isFinite(n) ? n / 100 : NaN;
  }
  return Number(value);
}

function fmtPct(value) {
  const n = frac(value);
  return Number.isFinite(n) ? `${(n * 100).toFixed(1)}%` : "--";
}
