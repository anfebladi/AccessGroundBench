# Web UI design system

The token reference for `src/webui/static/style.css`. Every value here is a CSS custom
property defined once in the `TOKENS` layer at the top of that file; nothing in the UI
should hard-code a colour, size or duration.

**Constraint that shapes all of it:** no Node, no build step, no CDN, no CSS framework.
The UI ships as flat files in `static/`, covered by `pyproject.toml`'s
`webui = ["static/*"]`. Layers inside `style.css` do the job a preprocessor would:
`FONTS → TOKENS → BASE → LAYOUT → COMPONENTS → UTILITIES → RESPONSIVE`.

**Register:** modern product craft (Linear / Raycast / Vercel), not a marketing page or a
SaaS form. Density and restraint carry the distinctiveness — a 14px UI base, a hairline
border doing the separating instead of a heavy shadow, one typeface instead of three
fighting each other. This is a second pass over the palette-only work in PR #29/#30; where
this doc contradicts an earlier stated doctrine, this one is current.

---

## 1. Typography

Self-hosted, one family, two roles. **Geist** (Vercel's general-purpose product sans, SIL
OFL 1.1, self-hosted variable woff2) replaced the previous three-face split — Inter for
body, Oswald for headings, IBM Plex Mono for numerals. Oswald was a signage face wrong for
a data tool; Geist is built for interfaces, so weight carries the heading/body distinction
instead of a family swap: 600 for headings, 500 for UI labels, 400 for body. Numerals and
code stay on **Geist Mono** — neither of the other two roles gives you tabular figures.

| Role | Token | Family | Used for |
|---|---|---|---|
| Display | `--font-display` | Geist (variable 400–600), weight 600 | Brand mark, h1–h3, card titles, pane titles, empty-state titles |
| UI | `--font-ui` | Geist (variable 400–600) | Body, lead paragraphs, controls, everything read at length |
| Mono | `--font-mono` | Geist Mono (variable 400–600) | Numerals, code, IDs, paths only — **not** chrome labels (rail groups, `.kv` terms, `.note-label` are all `--font-ui` now) |

Bundled files, both families SIL OFL 1.1 — the licence ships beside them in
`static/FONTS-LICENSE.txt` because the licence requires it:

```
geist.woff2         29,400 B   variable 400-600, latin
geistmono.woff2      23,128 B   variable 400-600, latin
```

`font-display: swap`, so a missing or slow font never blocks render.

### Scale

**14px UI base** (down from an inflated 17px — the single biggest lever on reading as a
product rather than a marketing page; Linear/Vercel/Raycast all sit near 13–14px), 15px
for prose. View titles dropped from 40px to ~26px. Small negative tracking on display
sizes — Geist isn't condensed the way Oswald was, so this doesn't double up the way it did
in the previous pass.

| Token | Size | Line-height | Tracking | Use |
|---|---:|---:|---:|---|
| `--text-display` | 1.625rem (26px) | 1.2 | −0.02em | View title |
| `--text-h2` | 1.25rem (20px) | 1.3 | −0.015em | Section heading |
| `--text-h3` | 1rem (16px) | 1.4 | −0.005em | Card heading |
| `--text-lead` | 0.9375rem (15px) | 1.55 | — | Lead paragraph |
| `--text-body` | 0.875rem (14px) | 1.5 | — | Body, controls |
| `--text-sm` | 0.8125rem (13px) | 1.45 | — | Table cells, hints |
| `--text-xs` | 0.75rem (12px) | 1.35 | +0.03em | Labels, overlines |

**Before:** a 17px base with 40px view titles and Oswald headings — the previous pass's
own "a little bigger across the board" doctrine, which read as a marketing page rather
than a tool once the rest of the redesign made density the point.

Every numeral carries `font-variant-numeric: tabular-nums` so columns align.

---

## 2. Colour

The six-stop navy-to-white blue ramp is **unchanged** from the previous pass — it was
never the problem (`#011f4b · #03396c · #005b96 · #6497b1 · #b3cde0 · #ffffff`). What
changed is the neutral ramp underneath it: the old `--border`/`--surface-2`/`--surface-3`
were `color-mix()` blue tints, which read as dated regardless of the accent sitting on
top. They're a true 12-step neutral ramp now (`--gray-50` … `--gray-950`), and only a
handful of stops are consumed by name — the rest exist for future components, which is
normal design-system practice, not dead weight.

| Role | Value |
|---|---|
| `--bg` / `--surface` | `#ffffff` |
| `--surface-2` | `--gray-50` (`#fafafa`) |
| `--surface-3` | `--gray-100` (`#f4f4f5`) |
| `--border` | `--gray-200` (`#e4e4e7`) — a true hairline now, not a blue tint |
| `--border-strong` | `--gray-300` (`#d4d4d8`) |
| `--text` | `#011f4b` |
| `--text-2` | `#03396c` |
| `--muted` / `--primary` | `#005b96` |
| `--ok` / `--warn` / `--err` | `#3d6b1f` / `#755509` / `#a3301f` — status colour, kept outside the brand ramp |

**One rule still drives every text pairing:** a light surface always carries dark-navy
text, a dark surface always carries white or pale-blue text — never the reverse.

### Dark data surfaces

A deep, near-black neutral for screenshots, charts and the comparison stage —
**not** the brand navy (`--forest` is still that, kept for the few small accents that want
brand colour regardless of context). Captured phone screens are already dark; putting them
on a light grey card made them look pasted on. This is a fixed, intentional design
element, not a dark theme the page follows — see §0 below for why that distinction matters.

| Token | Value | Used for |
|---|---|---|
| `--panel-dark` | `#0a0a0c` | Screenshot panes, chart panels, the Compare stage |
| `--panel-dark-2` | `#151517` | Nested surfaces on a dark panel (pane headers) |
| `--on-dark` | `#f4f4f5` | Primary text on a dark surface |
| `--on-dark-muted` | `#a1a1aa` | Secondary text on a dark surface |
| `--on-dark-border` | `rgba(255,255,255,0.08)` | Hairline visible on `--panel-dark` |

### Measured contrast

Computed, not eyeballed — every figure below is from an actual WCAG relative-luminance
calculation, not an estimate.

| Pair | Ratio |
|---|---:|
| `--text` on `--surface` | 16.17:1 |
| `--text-2` on `--surface` | 11.63:1 |
| `--muted`/`--primary` on `--surface` | 7.15:1 |
| `--primary-fg` on `--primary` (button) | 7.15:1 |
| `--ok` on `--surface` | 6.32:1 |
| `--warn` on `--surface` | 6.86:1 |
| `--err` on `--surface` | 7.00:1 |
| `--on-dark` on `--panel-dark` | 18.00:1 |
| `--on-dark-muted` on `--panel-dark` | 7.72:1 |
| `--on-dark` on `--panel-dark-2` | 16.59:1 |
| `--on-dark-muted` on `--panel-dark-2` | 7.12:1 |
| `--moss` on `--surface` (non-text fill only) | 3.18:1 |

All text pairs clear 4.5:1; `--moss` clears the 3:1 floor that applies to non-text UI and
data marks, and is deliberately never used for text.

### 0. Why the page still has no dark *mode*

Every reference for this register (Linear, Raycast, Vercel) keeps the page canvas light —
dark is confined to specific surfaces (code blocks, data panels), not the whole UI. The
original objection to a full dark theme (docs history: following the OS on a schedule the
user doesn't control would reintroduce exactly the wall-to-wall colour the palette pass
removed) still holds and hasn't been revisited. The dark data-surface tokens above are a
*different thing*: a fixed, intentional design element applied to specific components
(screenshots, charts) regardless of OS preference, not a page-wide theme toggle.
`color-scheme: light` in the root token block stops native form controls from rendering
dark on their own even when the OS prefers it.

### Chart palette (separate, separately validated)

`--viz-blue` `--viz-orange` `--viz-red` `--viz-neutral` are **not** UI colours. Measured
against `--panel-dark`, the surface every chart now sits on by default: viz-blue 4.48:1,
viz-orange 6.18:1, viz-red 5.00:1, viz-neutral 5.51:1 — all clear the 3:1 floor that
applies to marks and lines (not the 4.5:1 body-text floor; no chart draws body text in a
viz-* colour, only marks and lines). `--viz-neutral` is the diverging midpoint and is
deliberately achromatic, so it is exempt from the categorical chroma floor; because it
sits closest to the CVD gate against `--viz-red`, the stacked chart (`directionChart` in
`charts.js`) direct-labels every segment with its count rather than relying on hue alone.

---

## 3. Spacing

`--space-1…8` = `4 · 8 · 12 · 16 · 24 · 32 · 48 · 64px` (unchanged).

| Context | Value |
|---|---|
| Card padding | 16px (`<xl`) → 24px (`≥xl`) |
| Page gutter | 16px (`<md`) → 24px → 32px (`≥xl`) |
| Content max-width | 1360px; prose capped at `68ch` |

---

## 4. Radii, elevation and density

**Three radius tiers, not two:** `--radius-sm: 6px` (inline code, small marks) ·
`--radius-md: 8px` (buttons, inputs, rail rows) · `--radius-lg: 10px` (cards, panels,
drawer, image frames) · `--radius-full: 999px` (pills, progress) unchanged. **Before:**
10/14px, and before that an inconsistent 5/6/9/10/14px — this pass tightens the geometry
again to match the smaller control sizes below.

**Border-first, shadow-minimal** — the reverse of the previous pass's shadow-only cards,
which was a design error: this register (Linear/Vercel/Raycast) separates resting
surfaces with a hairline border and uses shadow only as a faint lift, never as the primary
separator. `.card` carries `border: 1px solid var(--border)` again, plus a much fainter
`--elev-card` than before.

| Token | Use |
|---|---|
| `--elev-card` | Cards, panels, button/segmented hover feedback — a faint lift, not a separator |
| `--elev-overlay` | The sticky run header (`.run-panel`), the drawer — anything that floats over scrolling content and needs a stronger cue regardless of what's behind it |

Exceptions: `.card-primary`'s tinted border marks the view's primary card (unchanged
purpose, now redundant with the plain border everywhere — it reads as a colour difference
on an already-bordered surface, not as the only border on the page); inputs/selects always
keep a border, shadowed surface or not; `.app-header` keeps **both** border and shadow —
sticky chrome with content scrolling underneath needs a reliable division line a shadow
alone can't guarantee; the drawer keeps its border too, since it floats over a dimmed
backdrop, not the plain page, so the card reasoning doesn't transfer.

### Density

**32px default control height** (`--control-h`), down from a uniform 44px — product
density, not touch density. `--control-h-sm: 28px` for `button.small`. `--tap: 44px`
remains the WCAG touch-target minimum, but it's applied conditionally now (see §6), not
baked into every control's resting size.

---

## 5. Component states

Applied to every interactive element, not just `<button>`.

| Element | hover | active | focus-visible | disabled | loading | error |
|---|---|---|---|---|---|---|
| Button ×4 variants | darker fill + `--elev-card` | darkest fill, no shadow, no translate | 2px ring, 2px offset | 45% opacity, no pointer | spinner + `aria-busy`, label kept | — |
| Input / select | `border-strong` → `text-2` | — | primary border + 3px soft ring | `surface-2`, muted text | — | `aria-invalid` + red border + message |
| Checkbox | outline on the box | — | ring | dimmed | — | — |
| Rail item | `surface-2` | — | ring | — | — | — |
| Segmented / chip | 6% ink wash | `aria-pressed` raised chip | ring | dimmed | — | — |
| Table row | `surface-2` | — | ring (actionable) | — | skeleton rows | — |

Loading keeps the label in place so the button does not resize and shift its neighbours;
`aria-busy` carries the state to assistive tech. Errors are never the red border alone —
`aria-invalid` exposes them programmatically and a message states what is wrong. No press
translate on `:active` for either pass — the colour change alone is enough feedback.

**Select.** `appearance: none` so a `<select>` matches the text input beside it instead of
rendering the OS's own control; the dropdown affordance is redrawn as a self-hosted inline
SVG chevron (no icon font, no CDN), muted further on `:disabled`. `select[multiple]` opts
back into the native `appearance: auto` — a listbox has no dropdown to hint at.

**`.note`.** Neutral is the default; colour is earned. `.note` (grey, `--muted`),
`.note-info` (blue, `--primary`) for a headline finding rather than a fault, `.note-warn`
(amber, `--warn`) for a genuine actionable warning. A 3px left rule and an uppercase
`.note-label`, never a filled background — a tinted box made every note read as alarming
regardless of what it said.

**Icons.** `src/webui/static/icons.js` — ~30 inline SVGs, `currentColor`-only so a glyph
inherits its container's text colour with no extra CSS. No icon font, matching the rest of
the offline-first constraint. The rail's step icons (`icons.js`'s `dataset`/`models`/
`evaluate`/`collect`/`compare`/`results`/`analyze`) are filled in by `app.js`'s
`populateRailIcons()` at startup — `index.html` carries only the `data-icon` key, so
`icons.js` stays the one place a glyph's path data lives.

**Skeletons** (`.skeleton`) replace bare "Loading…" text wherever the result's shape is
known, so the layout does not jump when data lands. It's the **only** looping animation in
the UI (see Motion below) and stops the instant real content lands.

### Motion

Four durations, each tied to a specific use, not to taste:

| Token | Duration | Use |
|---|---:|---|
| `--dur-fast` | 120ms | Colour, border, focus |
| `--dur-mid` | 180ms | Elevation, small transforms |
| `--dur-slow` | 240ms | Panels, drawer, view changes |
| `--dur-chart` | 400ms | Chart draw-in — **first render only** |

Explicitly excluded: looping animation (besides the skeleton shimmer, the one deliberate
exception), spring/bounce overshoot, parallax, decorative motion, staggered cascades.
Chart draw-in (`.chart-mark` for bars, `.chart-row` for dumbbell's line-and-dots — see
`charts.js`'s own header comment) is wired per-view with explicit "has this exact result
set already animated" tracking (`view-compare.js`'s `animatedChartKey`,
`view-analyze.js`/`view-results.js`'s `shouldAnimate` flag, consumed once per fetch) so a
filter click or profile-picker change never replays it. Everything collapses to ~0 under
`prefers-reduced-motion: reduce` (§8).

---

## 6. Layout, responsiveness and touch targets

Breakpoints: **sm 480 · md 768 · lg 1024 · xl 1280** (unchanged).

| Width | Behaviour |
|---|---|
| ≥ xl | 32px gutters, 24px card padding |
| ≥ lg | Two-column shell, `232px` rail |
| < lg | Rail becomes a horizontally scrollable tab strip |
| < md | Comparison stacks; Results table becomes one card per row; `.kv` stacks; drawer goes full-screen |
| < sm | Header meta hidden, field rows stack |

The mobile table is not a horizontal scroller: `thead` is visually hidden and each `<td>`
carries `data-label`, rendered as the field name beside its value.

**Touch targets are pointer-conditional, not viewport-conditional.** The previous pass
enforced 44px for every control under one width breakpoint; that conflated "narrow window"
with "touch input" and missed a touch laptop at full width. Controls now default to 32px
(`--control-h`) regardless of viewport, and
`@media (max-width: 767px), (pointer: coarse)` bumps every interactive element to
`--tap: 44px` — firing on *either* condition, so a touch device gets proper targets at any
window size, and a narrow mouse-driven window still gets the accessibility floor it had
before. This is *stronger* than the previous rule, not a relaxation of it.

---

## 7. CTA hierarchy

One filled primary action per view; everything else demotes.

| View | Primary |
|---|---|
| Dataset | — (a reading view) |
| Models | Add model |
| Evaluate | Start evaluation |
| Collect | Start collection |
| Compare | — (a reading view; the model/mode pickers are the only controls) |
| Results | — (a reading view) |
| Analyze | Run analysis |

`secondary` (outlined) for supporting actions, `ghost` for tertiary, `danger` reserved for
cancel/destructive.

---

## 8. Accessibility commitments

A benchmark measuring accessibility settings has no business failing these.

- One focus treatment for everything keyboard-reachable; `outline` is never removed
  without a replacement ring. Dark surfaces get their own ring (`.on-dark
  :focus-visible`) — the default primary-blue ring loses definition against
  near-black.
- Status is never colour alone: badges carry a dot **and** a text label, chart
  significance is filled-vs-hollow, underpowered rows carry `†`, stacked segments are
  direct-labelled, and the Compare view's three-state significance badge
  (`.badge.sig-yes` / `.sig-no` / `.sig-underpowered`) is worded, not colour-only —
  see `src/webui/compare.py`'s docstring for why a plain significant/not-significant
  binary would misrepresent the data.
- `aria-current` (rail, filmstrip), `aria-live="polite"` (run status), `aria-busy`
  (loading buttons), `aria-invalid` (fields), `role="alert"` (errors).
- Usable at 200% zoom and 400px width.
- `prefers-reduced-motion: reduce` collapses every animation and transition.
- Touch targets are guaranteed on any coarse-pointer device regardless of window size,
  not just below a width breakpoint (§6).
