"use strict";

/** Shared rendering helpers. No DOM ownership -- every function returns markup
 *  or a detached node, so views stay responsible for where things land. */

export function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

/**
 * Tagged template that escapes every interpolation.
 *
 *   html`<p>${userText}</p>`
 *
 * Values that are already trusted markup (built by another helper here) must be
 * wrapped in raw(): html`<div>${raw(badge("ok", "done"))}</div>`. Arrays are
 * joined, so `${rows.map(...)}` works without a .join("").
 */
export function html(strings, ...values) {
  return strings.reduce((out, chunk, i) => {
    if (i === 0) return chunk;
    return out + interpolate(values[i - 1]) + chunk;
  }, "");
}

const RAW = Symbol("raw");

export function raw(markup) {
  return { [RAW]: String(markup ?? "") };
}

function interpolate(value) {
  if (value === null || value === undefined || value === false) return "";
  if (Array.isArray(value)) return value.map(interpolate).join("");
  if (typeof value === "object" && RAW in value) return value[RAW];
  return escapeHtml(value);
}

// ---------- Status atoms ----------

/** kind: ok | warn | err | muted | info */
export function badge(kind, text) {
  return html`<span class="badge ${raw(kind)}">${text}</span>`;
}

export function stateLoading(text = "Loading...") {
  return html`<p class="state-loading">${text}</p>`;
}

export function stateError(text) {
  return html`<p class="state-error" role="alert">${text}</p>`;
}

/**
 * Shaped placeholder for content that is still loading.
 *
 * Preferred over a bare "Loading..." wherever the shape of the result is known:
 * the layout does not jump when the data lands, and the page does not flash a
 * line of text for 200ms.
 */
export function skeleton({ rows = 5, block = false } = {}) {
  if (block) return '<div class="skeleton skeleton-block" aria-hidden="true"></div>';
  const bars = Array.from({ length: rows },
    () => '<div class="skeleton skeleton-row"></div>').join("");
  return `<div aria-hidden="true">${bars}</div>`;
}

/**
 * Put a button into its loading state, and return a restore function.
 *
 * aria-busy carries the state to assistive tech; the label is deliberately kept
 * so the button does not resize and shift everything beside it.
 */
export function setLoading(button, loading, busyLabel) {
  if (!button) return () => {};
  const original = button.dataset.idleLabel ?? button.textContent;
  if (loading) {
    button.dataset.idleLabel = original;
    button.setAttribute("aria-busy", "true");
    button.disabled = true;
    if (busyLabel) button.textContent = busyLabel;
  } else {
    button.removeAttribute("aria-busy");
    button.disabled = false;
    button.textContent = original;
    delete button.dataset.idleLabel;
  }
  return () => setLoading(button, false);
}

/**
 * Mark a field invalid with a message beneath it.
 *
 * The red border never carries the failure on its own -- aria-invalid exposes
 * it programmatically and the message states what is actually wrong.
 */
export function setFieldError(input, messageHost, message) {
  if (input) {
    if (message) input.setAttribute("aria-invalid", "true");
    else input.removeAttribute("aria-invalid");
  }
  if (messageHost) {
    messageHost.innerHTML = message ? html`<p class="field-error">${message}</p>` : "";
  }
}

/**
 * First-run / no-data panel. `action` is optional trusted markup (a button or
 * link) rendered under the body -- an empty state that only says "nothing here"
 * leaves the user stuck, so every caller is nudged to offer the next step.
 */
export function emptyState({ title, body, action }) {
  return html`
    <div class="empty-state">
      <p class="empty-state-title">${title}</p>
      ${body ? raw(html`<p class="empty-state-body">${body}</p>`) : ""}
      ${action ? raw(`<div class="empty-state-action">${action}</div>`) : ""}
    </div>
  `;
}

// ---------- Formatting ----------

export function pct(value, digits = 1) {
  if (value === null || value === undefined || value === "") return "--";
  const n = Number(value);
  return Number.isFinite(n) ? `${(n * 100).toFixed(digits)}%` : "--";
}

/** Compact clock for run durations: 42s, 7m 05s, 1h 12m. */
export function duration(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "--";
  const s = Math.floor(seconds);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${String(s % 60).padStart(2, "0")}s`;
  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m`;
}

// ---------- DOM ----------

/**
 * Resolve a CSS custom property to its current value.
 *
 * Canvas and SVG strokes cannot reference var(), so overlay colours are read
 * from the same tokens the stylesheet uses -- otherwise dark mode would keep
 * drawing the light-theme palette onto every screenshot.
 */
export function cssVar(name, fallback = "#000") {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

/**
 * Draw an image into a canvas, then run `decorate(ctx, img)` for overlays.
 * Every view that shows a screenshot needs the same load/error/scale dance;
 * the error path draws a readable message instead of leaving a blank canvas.
 */
export function drawScreenshot(canvas, src, decorate) {
  const ctx = canvas.getContext("2d");
  const img = new Image();
  img.onload = () => {
    canvas.width = img.width;
    canvas.height = img.height;
    ctx.drawImage(img, 0, 0);
    if (decorate) decorate(ctx, img);
  };
  img.onerror = () => {
    canvas.width = 400;
    canvas.height = 80;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#b3221a";
    ctx.font = "14px sans-serif";
    ctx.fillText("Screenshot not available", 12, 44);
  };
  img.src = src;
  return img;
}

/** Line width that stays visible whatever the capture resolution is. */
export function strokeWidthFor(img) {
  return Math.max(2, img.width / 300);
}
