"use strict";

/**
 * Global keyboard shortcuts: view switching and the command palette.
 *
 * One document-level keydown listener, ignored whenever focus sits in an
 * editable field so a shortcut never fights with typing -- the same guard
 * the miss inspector and comparison stage already apply locally to their
 * own keys.
 */

import { openPalette } from "./command-palette.js";

const TAB_KEYS = {
  "1": "dataset", "2": "models", "3": "evaluate", "4": "collect",
  "5": "compare", "6": "results", "7": "analyze",
};

function isEditable(el) {
  if (!el) return false;
  const tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable;
}

export function initKeyboard() {
  document.addEventListener("keydown", (e) => {
    const mod = e.metaKey || e.ctrlKey;
    if (mod && e.key.toLowerCase() === "k") {
      e.preventDefault();
      openPalette();
      return;
    }
    if (isEditable(e.target) || mod || e.altKey) return;
    const tab = TAB_KEYS[e.key];
    if (tab) {
      e.preventDefault();
      location.hash = `#${tab}`;
    }
  });
}
