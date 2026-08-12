"use strict";

/**
 * Ctrl/Cmd+K command palette: jump to any view, screen, or configured model,
 * or trigger a handful of common actions. A single flat list filtered as
 * you type -- the roster (7 views + screens + models + a few actions) is
 * small enough that a filter beats a categorised menu.
 *
 * Standard combobox pattern: focus never leaves the text input, and the
 * arrow keys move a highlighted option that `aria-activedescendant` points
 * assistive tech at -- simpler and just as accessible as a real focus trap
 * across multiple elements, and it's the pattern most command palettes use.
 */

import { getModels } from "./view-models.js";
import { html, raw } from "./ui.js";

let getDataset = () => null;
let getScreens = () => [];
let onSelectScreen = () => {};

const VIEWS = [
  ["dataset", "Dataset"], ["models", "Models"], ["evaluate", "Evaluate"],
  ["collect", "Collect"], ["compare", "Compare"], ["results", "Results"], ["analyze", "Analyze"],
];

const ACTIONS = [
  ["Run an evaluation", "evaluate"],
  ["Run an analysis", "analyze"],
  ["Compare a model against baseline", "compare"],
  ["Collect a new dataset", "collect"],
];

let items = [];
let filtered = [];
let activeIndex = 0;
let isOpen = false;

export function initCommandPalette(deps) {
  getDataset = deps.getDataset;
  getScreens = deps.getScreens;
  onSelectScreen = deps.onSelectScreen;

  document.getElementById("palette-trigger")?.addEventListener("click", openPalette);
  const backdrop = document.getElementById("palette-backdrop");
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) closePalette();
  });
  const input = document.getElementById("palette-input");
  input.addEventListener("input", () => filterItems(input.value));
  input.addEventListener("keydown", handleKeydown);
}

export function openPalette() {
  if (isOpen) return;
  isOpen = true;
  buildItems();
  document.getElementById("palette-backdrop").hidden = false;
  const input = document.getElementById("palette-input");
  input.value = "";
  filterItems("");
  input.focus();
  document.addEventListener("keydown", escListener);
}

export function closePalette() {
  if (!isOpen) return;
  isOpen = false;
  document.getElementById("palette-backdrop").hidden = true;
  document.removeEventListener("keydown", escListener);
}

function escListener(e) {
  if (e.key === "Escape") closePalette();
}

function buildItems() {
  const dataset = getDataset();
  const screens = dataset ? getScreens() : [];
  const models = getModels();

  items = [
    ...VIEWS.map(([hash, label]) => ({
      label, hint: "View", go: () => { location.hash = `#${hash}`; },
    })),
    ...screens.map((s) => ({
      label: s, hint: "Screen",
      go: () => { location.hash = "#dataset"; onSelectScreen(s); },
    })),
    ...models.map((m) => ({
      label: m.id, hint: "Model", go: () => { location.hash = "#models"; },
    })),
    ...ACTIONS.map(([label, hash]) => ({
      label, hint: "Action", go: () => { location.hash = `#${hash}`; },
    })),
  ];
}

function filterItems(query) {
  const q = query.trim().toLowerCase();
  filtered = !q ? items : items.filter((it) => it.label.toLowerCase().includes(q));
  // A prefix match surfaces before a substring match, so a short query on a
  // large roster ("data") lands on the obvious hit ("Dataset") first.
  filtered.sort((a, b) => {
    const as = a.label.toLowerCase().startsWith(q) ? 0 : 1;
    const bs = b.label.toLowerCase().startsWith(q) ? 0 : 1;
    return as - bs;
  });
  activeIndex = 0;
  renderList();
}

function renderList() {
  const list = document.getElementById("palette-list");
  const input = document.getElementById("palette-input");

  if (!filtered.length) {
    list.innerHTML = `<li class="palette-empty muted small">No matches</li>`;
    input.removeAttribute("aria-activedescendant");
    return;
  }

  list.innerHTML = filtered.map((it, i) => html`
    <li role="option" id="palette-opt-${i}" class="${raw(i === activeIndex ? "is-active" : "")}"
        aria-selected="${String(i === activeIndex)}" data-index="${i}">
      <span class="palette-item-label">${it.label}</span>
      <span class="palette-item-hint">${it.hint}</span>
    </li>`).join("");

  input.setAttribute("aria-activedescendant", `palette-opt-${activeIndex}`);
  list.querySelectorAll("li[data-index]").forEach((li) => {
    li.addEventListener("click", () => selectIndex(Number(li.dataset.index)));
  });
  list.querySelector(".is-active")?.scrollIntoView({ block: "nearest" });
}

function selectIndex(i) {
  const item = filtered[i];
  if (!item) return;
  closePalette();
  item.go();
}

function handleKeydown(e) {
  if (e.key === "ArrowDown") {
    e.preventDefault();
    activeIndex = Math.min(filtered.length - 1, activeIndex + 1);
    renderList();
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    activeIndex = Math.max(0, activeIndex - 1);
    renderList();
  } else if (e.key === "Enter") {
    e.preventDefault();
    selectIndex(activeIndex);
  } else if (e.key === "Escape") {
    closePalette();
  }
}
