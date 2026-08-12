"use strict";

/**
 * localStorage-backed saved comparison-stage presets.
 *
 * Pure key/value helpers -- no DOM, no dependency on compare-stage.js or any
 * other view. A "view" is just a name plus whatever config object the caller
 * hands it; this module doesn't know or care what the keys inside mean.
 */

const KEY = "agb.savedViews.v1";

function readAll() {
  try {
    const raw = localStorage.getItem(KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch (e) {
    return [];
  }
}

function writeAll(views) {
  try {
    localStorage.setItem(KEY, JSON.stringify(views));
  } catch (e) {
    // Storage disabled or full: saved views just don't persist this session.
  }
}

/** Newest first. */
export function listViews() {
  return readAll().sort((a, b) => b.savedAt - a.savedAt);
}

export function saveView(name, config) {
  const views = readAll().filter((v) => v.name !== name);
  views.push({ name, config, savedAt: Date.now() });
  writeAll(views);
  return listViews();
}

export function deleteView(name) {
  writeAll(readAll().filter((v) => v.name !== name));
  return listViews();
}
