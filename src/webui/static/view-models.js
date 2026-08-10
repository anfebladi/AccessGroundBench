"use strict";

/**
 * Models view: provider credentials, the model catalog, and the single-query
 * smoke test that catches a wrong coordinate convention, a malformed model id,
 * or a bad key before a full run spends ~1000 paid calls finding out.
 */

import { api, enc, imageUrl } from "./api.js";
import {
  badge, cssVar, drawScreenshot, emptyState, html, raw,
  setFieldError, setLoading, stateError, stateLoading, strokeWidthFor,
} from "./ui.js";

const EXAMPLE_MODELS = [
  ["openai/gpt-4o-mini", "pixel"],
  ["gemini/gemini-2.0-flash", "norm1000"],
  ["ollama/llama3.2-vision:11b", "pixel"],
];

let models = [];
let onModelsChanged = () => {};

export function getModels() {
  return models;
}

export function initModelsView({ onChange }) {
  onModelsChanged = onChange || (() => {});
  models = readStoredModels();

  document.getElementById("add-model-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const input = document.getElementById("model-id-input");
    const id = input.value.trim();
    const errorHost = document.getElementById("add-model-error");
    setFieldError(input, errorHost, null);
    if (!id) return;
    if (models.some((m) => m.id === id)) {
      setFieldError(input, errorHost, `${id} is already configured.`);
      input.focus();
      return;
    }
    models.push({ id, coord_space: document.getElementById("model-coord-space").value });
    persist();
    input.value = "";
    renderModelList();
  });
}

function readStoredModels() {
  try {
    const parsed = JSON.parse(localStorage.getItem("agb_models") || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch (e) {
    return [];
  }
}

function persist() {
  localStorage.setItem("agb_models", JSON.stringify(models));
  onModelsChanged();
}

// ---------- Providers ----------

export async function loadProviders() {
  const tbody = document.querySelector("#provider-table tbody");
  let providers;
  try {
    providers = await api("/api/providers");
  } catch (e) {
    tbody.innerHTML = html`<tr><td colspan="4">${raw(stateError(e.message))}</td></tr>`;
    return;
  }

  tbody.innerHTML = providers.map((p) => {
    const kind = p.configured ? "ok" : "muted";
    const text = p.env_configured ? "From .env"
      : p.session_configured ? "Session key"
      : "Not configured";
    return html`
      <tr>
        <td><b>${p.provider}</b></td>
        <td><code>${p.env_vars.join(", ")}</code></td>
        <td>${raw(badge(kind, text))}</td>
        <td>
          <div style="display:flex; gap:var(--space-2); align-items:center;">
            <input type="password" placeholder="Paste key for this session"
                   aria-label="Session key for ${p.provider}"
                   data-provider="${p.provider}" style="width:15rem" />
            <button type="button" class="secondary small" data-set="${p.provider}">Set</button>
            ${p.session_configured
              ? raw(html`<button type="button" class="secondary small" data-clear="${p.provider}">Clear</button>`)
              : ""}
          </div>
        </td>
      </tr>`;
  }).join("");

  tbody.querySelectorAll("button[data-set]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const provider = btn.dataset.set;
      const input = tbody.querySelector(`input[data-provider="${provider}"]`);
      if (!input.value.trim()) return;
      await api("/api/keys", {
        method: "POST",
        body: JSON.stringify({ provider, value: input.value }),
      });
      input.value = "";
      await loadProviders();
    });
  });
  tbody.querySelectorAll("button[data-clear]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await api(`/api/keys/${enc(btn.dataset.clear)}`, { method: "DELETE" });
      await loadProviders();
    });
  });
}

// ---------- Model catalog ----------

export function renderModelList() {
  const host = document.getElementById("model-list");

  if (!models.length) {
    host.innerHTML = emptyState({
      title: "No models configured yet",
      body: "A model id is a LiteLLM model string. Add one above, or start from an example:",
      action: EXAMPLE_MODELS.map(([id, space]) => html`
        <button type="button" class="secondary small" data-example="${id}" data-space="${space}">${id}</button>
      `).join(""),
    });
    host.querySelectorAll("button[data-example]").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.getElementById("model-id-input").value = btn.dataset.example;
        document.getElementById("model-coord-space").value = btn.dataset.space;
        document.getElementById("model-id-input").focus();
      });
    });
    onModelsChanged();
    return;
  }

  host.innerHTML = html`
    <div class="table-wrap">
      <table>
        <thead><tr><th>Model</th><th>Coordinate space</th><th></th></tr></thead>
        <tbody>
          ${models.map((m) => raw(html`
            <tr>
              <td><code>${m.id}</code></td>
              <td>${m.coord_space === "norm1000" ? "Normalized (0-1000)" : "Pixel"}</td>
              <td style="text-align:right">
                <button type="button" class="secondary small" data-test="${m.id}">Test model</button>
                <button type="button" class="ghost small" data-remove="${m.id}">Remove</button>
              </td>
            </tr>`))}
        </tbody>
      </table>
    </div>
    <p class="field-hint" style="margin-top: var(--space-3);">
      Test model sends one real query against one target and draws the answer
      over the ground-truth box.
    </p>
  `;

  host.querySelectorAll("button[data-test]").forEach((btn) => {
    btn.addEventListener("click", () =>
      runSmokeTest(models.find((m) => m.id === btn.dataset.test), btn));
  });
  host.querySelectorAll("button[data-remove]").forEach((btn) => {
    btn.addEventListener("click", () => {
      models = models.filter((m) => m.id !== btn.dataset.remove);
      persist();
      renderModelList();
    });
  });
  onModelsChanged();
}

// ---------- Smoke test ----------

/* Resolved at click time, not at wiring time: the smoke test should run against
 * whichever screen is selected on the Dataset step right now. */
let smokeContext = { getDataset: () => null, getScreen: () => null };

export function setSmokeContext(getDataset, getScreen) {
  smokeContext = { getDataset, getScreen };
}

async function runSmokeTest(model, triggerBtn) {
  const host = document.getElementById("smoke-test-result");
  if (!model) return;
  const dataset = smokeContext.getDataset();
  const screen = smokeContext.getScreen();
  if (!dataset || !screen) {
    host.innerHTML = html`<div class="card">${raw(stateError("Select a dataset with at least one screen first."))}</div>`;
    return;
  }

  // A real provider call: it can take many seconds, so the button owns the
  // pending state rather than leaving the user unsure the click registered.
  const stopLoading = setLoading(triggerBtn, true, "Testing");
  host.innerHTML = html`<div class="card">${raw(stateLoading(`Querying ${model.id} on ${screen}...`))}</div>`;

  let result;
  try {
    result = await api("/api/smoke-test", {
      method: "POST",
      body: JSON.stringify({ dataset, model: model.id, screen, coord_space: model.coord_space }),
    });
  } catch (e) {
    host.innerHTML = html`<div class="card">${raw(stateError(`Request failed: ${e.message}`))}</div>`;
    return;
  } finally {
    stopLoading();
  }

  if (!result.ok) {
    host.innerHTML = html`<div class="card">${raw(stateError(result.error || "The model call failed."))}</div>`;
    return;
  }

  const verdict = result.hit === 1 ? badge("ok", "Hit")
    : result.hit === 0 ? badge("err", "Miss")
    : badge("warn", "Out of frame");

  host.innerHTML = html`
    <div class="card">
      <div class="card-head">
        <div>
          <h3>Test result -- ${model.id}</h3>
          <p class="card-sub">One query against <code>${screen}</code> at baseline.</p>
        </div>
        <div class="card-head-actions">${raw(verdict)}</div>
      </div>

      ${result.coord_space_mismatch ? raw(html`
        <div class="note">
          <b>Coordinate-space mismatch.</b> This reply looks like
          <code>${result.coord_space_detected}</code> but the model is configured
          as <code>${result.coord_space_used}</code>. Switch this model's
          coordinate space before a full run, or it will score near zero while
          appearing to answer normally.
        </div>`) : ""}

      <div class="row">
        <div class="grow">
          <dl class="kv">
            <dt>Target</dt><dd><b>${result.target_text}</b></dd>
            <dt>Latency</dt><dd>${result.latency_seconds.toFixed(2)}s</dd>
            <dt>Detected space</dt><dd><code>${result.coord_space_detected}</code></dd>
            <dt>Raw reply</dt><dd><code>${result.raw_response || ""}</code></dd>
          </dl>
        </div>
        <div>
          <div class="image-frame">
            <canvas id="smoke-canvas" style="max-height:52vh; width:auto;"></canvas>
          </div>
          <div class="overlay-legend" style="justify-content:center; margin-top:var(--space-2);">
            <span class="legend-item" style="color: var(--ok)"><span class="legend-swatch"></span>Ground truth</span>
            <span class="legend-item" style="color: var(--err)"><span class="legend-swatch filled"></span>Predicted point</span>
          </div>
        </div>
      </div>
    </div>
  `;

  const ok = cssVar("--ok", "#157a41");
  const err = cssVar("--err", "#b3221a");
  drawScreenshot(
    document.getElementById("smoke-canvas"),
    imageUrl(dataset, screen, "baseline"),
    (ctx, img) => {
      if (result.box) {
        ctx.strokeStyle = ok;
        ctx.lineWidth = strokeWidthFor(img);
        const [x1, y1, x2, y2] = result.box;
        ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
      }
      if (result.x_pred !== null && result.y_pred !== null) {
        ctx.fillStyle = err;
        ctx.beginPath();
        ctx.arc(result.x_pred, result.y_pred, Math.max(6, img.width / 80), 0, 2 * Math.PI);
        ctx.fill();
      }
    }
  );
}
