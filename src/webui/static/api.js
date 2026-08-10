"use strict";

/**
 * Thin fetch wrapper over the /api endpoints in webui/server.py.
 *
 * FastAPI reports failures as {"detail": "..."}; that message is worth far more
 * to the user than the status text, so it is unwrapped here and thrown as the
 * Error message. Every caller can then render `err.message` directly.
 */
export async function api(path, options) {
  const res = await fetch(path, options && {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (e) { /* ignore */ }
    throw new Error(detail);
  }
  const contentType = res.headers.get("content-type") || "";
  return contentType.includes("application/json") ? res.json() : res;
}

/** Path-segment encoder. Dataset and screen names reach the URL verbatim. */
export const enc = encodeURIComponent;

/** Cache-busting suffix for image URLs, which are re-fetched after a new run. */
export function imageUrl(dataset, screen, profile) {
  return `/api/datasets/${enc(dataset)}/image/${enc(screen)}/${enc(profile)}?_=${Date.now()}`;
}
