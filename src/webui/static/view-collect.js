"use strict";

/** Collect view: emulator preflight and a capture run, on the shared monitor. */

import { api } from "./api.js";
import { badge, html, raw, setLoading, stateError, stateLoading } from "./ui.js";
import { createRunMonitor } from "./runmonitor.js";

let onRunFinished = () => {};
let monitor = null;

export function initCollectView(deps) {
  onRunFinished = deps.onRunFinished || (() => {});
  document.getElementById("collect-preflight-btn").addEventListener("click", checkPreflight);
  document.getElementById("collect-form").addEventListener("submit", startRun);
  loadScreens();
}

async function loadScreens() {
  const select = document.getElementById("collect-screens");
  try {
    const { all_screens } = await api("/api/collect/screens");
    select.innerHTML = all_screens.map((s) => html`<option value="${s}">${s}</option>`).join("");
  } catch (e) {
    select.innerHTML = "";
  }
}

async function checkPreflight() {
  const out = document.getElementById("collect-preflight-result");
  out.innerHTML = stateLoading("Checking adb...");

  let info;
  try {
    info = await api("/api/collect/preflight");
  } catch (e) {
    out.innerHTML = stateError(e.message);
    return;
  }

  if (!info.adb_available) {
    out.innerHTML = html`
      ${raw(badge("err", "adb not found"))}
      <p class="field-hint">${info.error || "Install the Android platform tools and put adb on PATH."}</p>`;
    return;
  }
  if (info.error) {
    out.innerHTML = html`
      ${raw(badge("warn", "adb found, but listing devices failed"))}
      <p class="field-hint"><code>${info.adb_path}</code></p>
      <p class="field-hint">${info.error}</p>`;
    return;
  }

  const authorized = (info.devices || []).filter((d) => d.status === "device");
  if (!authorized.length) {
    out.innerHTML = html`
      ${raw(badge("warn", "adb is working, but no authorized device"))}
      <ul class="field-hint">
        ${(info.devices || []).map((d) => raw(html`<li><code>${d.serial}</code> -- ${d.status}</li>`))}
        ${!(info.devices || []).length ? raw("<li>No devices listed.</li>") : ""}
      </ul>`;
    return;
  }

  out.innerHTML = html`
    ${raw(badge("ok", `${authorized.length} authorized device${authorized.length === 1 ? "" : "s"}`))}
    <ul class="field-hint">
      ${authorized.map((d) => raw(html`<li><code>${d.serial}</code></li>`))}
    </ul>`;
}

async function startRun(e) {
  e.preventDefault();
  const errorHost = document.getElementById("collect-error");
  const runHost = document.getElementById("collect-run");
  errorHost.innerHTML = "";

  const payload = {
    name: document.getElementById("collect-name").value.trim(),
    screens: Array.from(document.getElementById("collect-screens").selectedOptions).map((o) => o.value),
    dry_run: document.getElementById("collect-dry-run").checked,
    rebuild_manifest: document.getElementById("collect-rebuild-manifest").checked,
  };

  const submitBtn = e.target.querySelector('button[type="submit"]');
  const stopLoading = setLoading(submitBtn, true, "Starting");

  let started;
  try {
    started = await api("/api/collect/runs", { method: "POST", body: JSON.stringify(payload) });
  } catch (err) {
    errorHost.innerHTML = stateError(err.message);
    stopLoading();
    return;
  }

  document.getElementById("collect-command").innerHTML = "";
  if (monitor) monitor.stop();
  // Collection has no per-item planned total the way evaluation does, so the
  // bar runs indeterminate and the tally stays empty rather than inventing one.
  monitor = createRunMonitor({
    mountEl: runHost,
    runId: started.run_id,
    command: started.equivalent_command,
    onFinish: async (status) => {
      stopLoading();
      await onRunFinished(status);
    },
  });
  runHost.scrollIntoView({ behavior: "smooth", block: "nearest" });
}
