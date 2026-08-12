"use strict";

/**
 * Inline SVG icon set. No icon font, no CDN -- the server must work offline,
 * and a font is a heavier, less crisp way to ship ~20 glyphs than embedding
 * them directly. Every icon is `currentColor`-only so it inherits text
 * colour from its container (rail link, button, badge) without extra CSS.
 *
 * Usage matches the `html`/`raw` pattern in ui.js: `icon()` returns a plain
 * SVG string, so callers wrap it in `raw()` when interpolating into a
 * template: `html`<span>${raw(icon("dataset"))}</span>``.
 */

const PATHS = {
  // -- Nav (rail) --
  dataset: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  models: '<circle cx="12" cy="12" r="3"/><path d="M12 2v4M12 18v4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M2 12h4M18 12h4M4.9 19.1l2.8-2.8M16.3 7.7l2.8-2.8"/>',
  evaluate: '<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
  collect: '<rect x="5" y="2" width="14" height="20" rx="2"/><path d="M9 18h.01"/><path d="M9 6h6"/>',
  results: '<path d="M3 3v18h18"/><rect x="7" y="13" width="3" height="5"/><rect x="12" y="9" width="3" height="9"/><rect x="17" y="5" width="3" height="13"/>',
  analyze: '<path d="M3 3v18h18"/><path d="M7 15l4-6 3 3 5-8"/>',
  compare: '<rect x="3" y="4" width="8" height="16" rx="1.5"/><rect x="13" y="4" width="8" height="16" rx="1.5"/><path d="M7 9v6M17 9v6"/>',

  // -- Status --
  check: '<path d="M20 6L9 17l-5-5"/>',
  "check-circle": '<circle cx="12" cy="12" r="9"/><path d="M8.5 12.5l2.5 2.5 5-5"/>',
  cross: '<path d="M18 6L6 18M6 6l12 12"/>',
  "cross-circle": '<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/>',
  warning: '<path d="M12 3l10 18H2L12 3z"/><path d="M12 10v4M12 17h.01"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 8h.01M11 12h1v5h1"/>',

  // -- Direction --
  "arrow-up": '<path d="M12 19V5M5 12l7-7 7 7"/>',
  "arrow-down": '<path d="M12 5v14M19 12l-7 7-7-7"/>',
  "chevron-up": '<path d="M6 15l6-6 6 6"/>',
  "chevron-down": '<path d="M6 9l6 6 6-6"/>',
  "chevron-left": '<path d="M15 6l-6 6 6 6"/>',
  "chevron-right": '<path d="M9 6l6 6-6 6"/>',

  // -- Actions --
  play: '<path d="M6 4l14 8-14 8V4z"/>',
  stop: '<rect x="5" y="5" width="14" height="14" rx="1.5"/>',
  download: '<path d="M12 3v13M6 11l6 6 6-6"/><path d="M4 20h16"/>',
  copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M20 20l-4.8-4.8"/>',
  "zoom-in": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M20 20l-4.8-4.8"/><path d="M10.5 7.5v6M7.5 10.5h6"/>',
  "zoom-out": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M20 20l-4.8-4.8"/><path d="M7.5 10.5h6"/>',
  layers: '<path d="M12 2l9 5-9 5-9-5 9-5z"/><path d="M3 12l9 5 9-5M3 17l9 5 9-5"/>',
  eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/>',
  keyboard: '<rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M6 14h12"/>',
  close: '<path d="M18 6L6 18M6 6l12 12"/>',
  "external-link": '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><path d="M15 3h6v6M10 14L21 3"/>',
  filter: '<path d="M4 4h16l-6 8v6l-4 2v-8L4 4z"/>',
  "sliders": '<path d="M4 6h9M17 6h3M4 12h3M9 12h11M4 18h13M20 18h0"/><circle cx="15" cy="6" r="2"/><circle cx="7" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
  command: '<path d="M9 3a3 3 0 0 0-3 3v12a3 3 0 1 0 3-3h6a3 3 0 1 0-3 3V6a3 3 0 1 0 3 3H9a3 3 0 1 0 3-3z"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/>',
  spinner: '<path d="M12 3a9 9 0 1 0 9 9"/>',
  bookmark: '<path d="M6 3h12a1 1 0 0 1 1 1v17l-7-4-7 4V4a1 1 0 0 1 1-1z"/>',
  trash: '<path d="M4 7h16M9 7V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v3M6 7l1 13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-13"/>',
};

/**
 * Return an inline SVG string for `name` at `size` pixels square.
 * `stroke-width` scales down slightly at larger sizes so thick glyphs
 * don't read as blobby once they're bigger than the ~16-20px they were
 * drawn for.
 */
export function icon(name, size = 16) {
  const body = PATHS[name];
  if (!body) return "";
  const strokeWidth = size >= 24 ? 1.5 : 2;
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${strokeWidth}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
}

/** The full set of registered icon names, for anything that wants to validate a name exists. */
export const ICON_NAMES = Object.keys(PATHS);
