"use strict";

/**
 * One run monitor for both Evaluate and Collect.
 *
 * Progress is derived on the client from the run's own stdout rather than from
 * a new endpoint: evaluation.runner prints exactly one line per query, and the
 * planned call count is already served by the preflight endpoint. Counting
 * those lines against that total gives a determinate bar with no backend
 * change and no second source of truth about how far along a run is.
 */

import { api } from "./api.js";
import { badge, duration, html, raw } from "./ui.js";

const POLL_MS = 1200;

/* Every per-target line evaluation.runner prints is a 4-space indent then a
 * bracketed token. Screen-level notices ([SKIP], [HARVEST]) use a 2-space
 * indent and are deliberately excluded -- they are not units of progress. */
const RESULT_LINE = /^ {4}\[(HIT|MISS|OFF-SCREEN|OFF-FRAME|LABEL-CHANGED|API-ERROR)\]/;

const TALLY_ORDER = [
  ["HIT", "Hit", "is-ok"],
  ["MISS", "Miss", ""],
  ["OFF-SCREEN", "Off-screen", ""],
  ["OFF-FRAME", "Off-frame", ""],
  ["LABEL-CHANGED", "Label changed", ""],
  ["API-ERROR", "API error", "is-err"],
];

/**
 * Mount a live run panel into `mountEl` and poll until the run ends.
 *
 * expectedTotal/alreadyDone come from the evaluate preflight; pass neither for
 * collect, where there is no meaningful per-item total and the bar falls back
 * to indeterminate.
 */
export function createRunMonitor({
  mountEl,
  runId,
  command,
  expectedTotal = null,
  alreadyDone = 0,
  onFinish = null,
}) {
  const counts = new Map();
  let done = 0;
  let since = 0;
  let status = "running";
  let timer = null;
  let stick = true;
  const startedAt = Date.now();

  mountEl.innerHTML = html`
    <div class="card run-panel">
      <div class="run-header">
        <div class="run-header-top">
          <div class="run-title">
            <span id="run-badge">${raw(badge("warn", "running"))}</span>
            <span class="run-counts" id="run-counts"></span>
          </div>
          <div class="run-title">
            <span class="run-timing" id="run-timing"></span>
            <button type="button" class="secondary small" id="run-cancel">Cancel run</button>
          </div>
        </div>
        <div class="progress" id="run-progress" role="progressbar"
             aria-label="Run progress" aria-valuemin="0">
          <div class="progress-fill" id="run-progress-fill" style="width:0%"></div>
        </div>
        <div class="tally" id="run-tally"></div>
        <p class="sr-only" id="run-live" aria-live="polite"></p>
      </div>
      <details class="run-log-wrap" id="run-log-details">
        <summary>Show raw log</summary>
        <pre id="run-log" tabindex="0"></pre>
        <p class="log-paused hidden" id="run-log-paused">
          Auto-scroll paused. <button type="button" class="ghost small" id="run-log-resume">Jump to latest</button>
        </p>
      </details>
      ${command ? raw(commandBlock(command)) : ""}
    </div>
  `;

  const el = (id) => mountEl.querySelector(`#${id}`);
  const logEl = el("run-log");
  const pausedEl = el("run-log-paused");

  el("run-cancel").addEventListener("click", async () => {
    el("run-cancel").disabled = true;
    try { await api(`/api/runs/${runId}/cancel`, { method: "POST" }); } catch (e) { /* run already ended */ }
  });

  // A run that scrolls itself while the user is reading earlier output is
  // fighting them; stop following once they scroll away from the bottom.
  logEl.addEventListener("scroll", () => {
    const atBottom = logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight < 12;
    if (atBottom !== stick) {
      stick = atBottom;
      pausedEl.classList.toggle("hidden", stick);
    }
  });
  el("run-log-resume").addEventListener("click", () => {
    stick = true;
    pausedEl.classList.add("hidden");
    logEl.scrollTop = logEl.scrollHeight;
  });

  const copyBtn = mountEl.querySelector("button[data-copy-run]");
  if (copyBtn) {
    copyBtn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(command);
        copyBtn.textContent = "Copied";
        setTimeout(() => { copyBtn.textContent = "Copy"; }, 1200);
      } catch (e) { copyBtn.textContent = "Select and copy"; }
    });
  }

  function ingest(lines) {
    for (const line of lines) {
      const match = RESULT_LINE.exec(line);
      if (!match) continue;
      counts.set(match[1], (counts.get(match[1]) || 0) + 1);
      done += 1;
    }
    if (!lines.length) return;
    logEl.textContent += lines.join("\n") + "\n";
    if (stick) logEl.scrollTop = logEl.scrollHeight;
  }

  function render() {
    const total = expectedTotal;
    const completed = alreadyDone + done;
    const elapsed = (Date.now() - startedAt) / 1000;

    const progress = el("run-progress");
    const fill = el("run-progress-fill");
    if (total) {
      const ratio = Math.min(1, completed / total);
      progress.classList.remove("is-indeterminate");
      progress.setAttribute("aria-valuemax", String(total));
      progress.setAttribute("aria-valuenow", String(completed));
      fill.style.width = `${(ratio * 100).toFixed(1)}%`;
      el("run-counts").textContent =
        `${completed} / ${total} queries (${Math.round(ratio * 100)}%)`;
    } else {
      progress.classList.toggle("is-indeterminate", status === "running");
      progress.removeAttribute("aria-valuenow");
      if (status !== "running") fill.style.width = "100%";
      el("run-counts").textContent = done ? `${done} queries` : "";
    }

    // ETA extrapolates from this session's own rate, so a resumed run is not
    // skewed by the calls a previous process already made.
    let timing = `${duration(elapsed)} elapsed`;
    if (status === "running" && total && done > 0) {
      const remaining = Math.max(0, total - completed);
      timing += ` -- about ${duration((elapsed / done) * remaining)} left`;
    }
    el("run-timing").textContent = timing;

    el("run-tally").innerHTML = TALLY_ORDER
      .filter(([key]) => counts.get(key))
      .map(([key, label, cls]) => html`
        <span class="tally-item ${raw(cls)}"><b>${counts.get(key)}</b> ${label}</span>
      `).join("");

    const kind = status === "running" ? "warn" : status === "completed" ? "ok" : "err";
    el("run-badge").innerHTML = badge(kind, status);
    el("run-cancel").classList.toggle("hidden", status !== "running");
    el("run-live").textContent = `Run ${status}. ${completed}${total ? ` of ${total}` : ""} queries done.`;
  }

  async function poll() {
    if (timer) clearTimeout(timer);
    let run;
    try {
      run = await api(`/api/runs/${runId}?since=${since}`);
    } catch (e) {
      // A transient poll failure should not silently freeze the panel.
      status = "failed";
      render();
      return;
    }
    ingest(run.lines || []);
    since = run.next_since;
    status = run.status;
    render();
    if (status === "running") {
      timer = setTimeout(poll, POLL_MS);
    } else {
      // The final poll can arrive with the log still buffering; one more read
      // drains whatever the reader thread appended after the status flipped.
      const tail = await api(`/api/runs/${runId}?since=${since}`).catch(() => null);
      if (tail && tail.lines && tail.lines.length) {
        ingest(tail.lines);
        since = tail.next_since;
        render();
      }
      if (onFinish) onFinish(status);
    }
  }

  render();
  poll();

  return {
    stop() { if (timer) clearTimeout(timer); },
    get status() { return status; },
  };
}

function commandBlock(command) {
  return html`
    <div class="run-log-wrap" style="padding-top:0;">
      <p class="command-label">Equivalent command</p>
      <div class="command-block">
        <code>${command}</code>
        <button type="button" class="secondary small" data-copy-run>Copy</button>
      </div>
    </div>
  `;
}

/** Shared error renderer for the two run-launching forms. */
export function renderLaunchError(mountEl, message) {
  mountEl.innerHTML = html`<p class="state-error">${message}</p>`;
}
