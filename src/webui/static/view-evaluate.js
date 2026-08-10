"use strict";

/**
 * Evaluate view: preflight (planned calls, resume position, stale lock), run
 * launch, and the live run panel.
 */

import { api, enc } from "./api.js";
import { badge, html, raw, setFieldError, setLoading, stateError } from "./ui.js";
import { createRunMonitor } from "./runmonitor.js";

let getDataset = () => null;
let getModels = () => [];
let onRunFinished = () => {};
let preflight = null;
let monitor = null;

export function initEvaluateView(deps) {
  getDataset = deps.getDataset;
  getModels = deps.getModels;
  onRunFinished = deps.onRunFinished || (() => {});

  document.getElementById("evaluate-form").addEventListener("submit", startRun);
  document.getElementById("eval-mode-select").addEventListener("change", refreshPreflight);
  document.getElementById("eval-model-select").addEventListener("change", () => {
    syncCoordSpace();
    refreshPreflight();
  });
}

/** Repopulate the model dropdown from the Models tab's catalog. */
export function syncModelOptions() {
  const select = document.getElementById("eval-model-select");
  const models = getModels();
  const previous = select.value;

  if (!models.length) {
    select.innerHTML = html`<option value="">No models configured</option>`;
    select.disabled = true;
    document.getElementById("eval-start").disabled = true;
    document.getElementById("eval-preflight").innerHTML = html`
      <div class="note" style="margin-top: var(--space-4);">
        Add a model on the <a href="#models">Models</a> step first, then come back here.
      </div>`;
    return;
  }

  select.disabled = false;
  document.getElementById("eval-start").disabled = false;
  select.innerHTML = models.map((m) => html`<option value="${m.id}">${m.id}</option>`).join("");
  if (models.some((m) => m.id === previous)) select.value = previous;

  // The coordinate space belongs to the model, so keep the advanced override
  // in step with the selection rather than making the user remember it.
  syncCoordSpace();
  refreshPreflight();
}

function syncCoordSpace() {
  const model = getModels().find((m) => m.id === document.getElementById("eval-model-select").value);
  if (model) document.getElementById("eval-coord-space").value = model.coord_space;
}

export async function refreshPreflight() {
  const host = document.getElementById("eval-preflight");
  const unlockHost = document.getElementById("eval-unlock-field");
  const dataset = getDataset();
  const model = document.getElementById("eval-model-select").value;

  unlockHost.innerHTML = "";
  if (!dataset || !model) { host.innerHTML = ""; return; }

  const useTree = document.getElementById("eval-mode-select").value === "tree";
  try {
    preflight = await api(
      `/api/datasets/${enc(dataset)}/preflight?model=${enc(model)}&use_a11y_tree=${useTree}`
    );
  } catch (e) {
    preflight = null;
    host.innerHTML = html`<div style="margin-top: var(--space-4);">${raw(stateError(e.message))}</div>`;
    return;
  }

  const remaining = preflight.expected_total - preflight.already_done;
  const resume = preflight.already_done > 0
    ? badge("info", `Resuming -- ${remaining} of ${preflight.expected_total} queries left`)
    : badge("muted", `${preflight.expected_total} queries planned`);

  host.innerHTML = html`
    <div style="margin-top: var(--space-4); display:flex; gap:var(--space-3); align-items:center; flex-wrap:wrap;">
      ${raw(resume)}
      <span class="field-hint">Writes to <code>${preflight.results_csv}</code></span>
    </div>
    ${preflight.lock_present ? raw(html`
      <div class="note">
        <b>This results file is locked.</b>
        ${preflight.lock_holder ? raw(html`Held by <code>${preflight.lock_holder}</code>.`) : ""}
        If no run is actually active -- a crashed process leaves its lock behind --
        enable <b>Override stale lock</b> under Advanced options, or this run
        will exit without doing anything.
      </div>`) : ""}
  `;

  // The override is only ever correct when a lock exists, so it is not offered
  // the rest of the time -- a checkbox that is always wrong to tick is a trap.
  if (preflight.lock_present) {
    unlockHost.innerHTML = html`
      <label class="check">
        <input id="eval-force-unlock" type="checkbox" />
        <span class="check-body">
          Override stale lock
          <span class="field-hint">Only if you are certain no other run is writing this file.</span>
        </span>
      </label>`;
  }
}

async function startRun(e) {
  e.preventDefault();
  const errorHost = document.getElementById("eval-error");
  const commandHost = document.getElementById("eval-command");
  const runHost = document.getElementById("eval-run");
  errorHost.innerHTML = "";

  const modelSelect = document.getElementById("eval-model-select");
  const model = modelSelect.value;
  if (!model) {
    setFieldError(modelSelect, errorHost, "Add a model on the Models step before starting a run.");
    modelSelect.focus();
    return;
  }
  setFieldError(modelSelect, errorHost, null);

  const forceUnlock = document.getElementById("eval-force-unlock");
  const fresh = document.getElementById("eval-fresh").checked;
  const payload = {
    dataset: getDataset(),
    model,
    use_a11y_tree: document.getElementById("eval-mode-select").value === "tree",
    trials: Number(document.getElementById("eval-trials").value) || 1,
    pace_seconds: Number(document.getElementById("eval-pace").value) || 0,
    coord_space: document.getElementById("eval-coord-space").value,
    fresh,
    force_unlock: Boolean(forceUnlock && forceUnlock.checked),
  };

  const startBtn = document.getElementById("eval-start");
  const stopLoading = setLoading(startBtn, true, "Starting");

  let started;
  try {
    started = await api("/api/runs", { method: "POST", body: JSON.stringify(payload) });
  } catch (err) {
    errorHost.innerHTML = stateError(err.message);
    stopLoading();
    return;
  }

  commandHost.innerHTML = "";
  if (monitor) monitor.stop();
  monitor = createRunMonitor({
    mountEl: runHost,
    runId: started.run_id,
    command: started.equivalent_command,
    expectedTotal: preflight ? preflight.expected_total : null,
    // A fresh run rewrites the file, so the resume offset no longer applies.
    alreadyDone: fresh || !preflight ? 0 : preflight.already_done,
    onFinish: async () => {
      stopLoading();
      await refreshPreflight();
      onRunFinished();
    },
  });
  runHost.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

export function preflightSummary() {
  if (!preflight) return "";
  const remaining = preflight.expected_total - preflight.already_done;
  if (!preflight.expected_total) return "";
  return preflight.already_done > 0
    ? `${remaining} queries left`
    : `${preflight.expected_total} queries planned`;
}
