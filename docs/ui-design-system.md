# Web UI design system

The token reference for `src/webui/static/style.css`. Every value here is a CSS custom
property defined once in the `TOKENS` layer at the top of that file; nothing in the UI
should hard-code a colour, size or duration.

**Constraint that shapes all of it:** no Node, no build step, no CDN, no CSS framework.
The UI ships as flat files in `static/`, covered by `pyproject.toml`'s
`webui = ["static/*"]`. Layers inside `style.css` do the job a preprocessor would:
`FONTS → TOKENS → BASE → LAYOUT → COMPONENTS → UTILITIES → RESPONSIVE`.

---

## 1. Typography

Self-hosted, three roles. One face for everything was the single biggest reason the
previous build read as a stock admin template.

| Role | Token | Family | Used for |
|---|---|---|---|
| Display | `--font-display` | Newsreader (variable 400–700) | Headings, lead paragraphs, pane titles |
| UI | `--font-ui` | system-ui stack | Body, controls, chart row labels |
| Mono | `--font-mono` | IBM Plex Mono 400/500 | All numerals, code, table heads, status labels |

Bundled files (~162 KB total), both families SIL OFL 1.1 — the licence ships beside them
in `static/FONTS-LICENSE.txt` because the licence requires it:

```
newsreader.woff2      132,000 B   variable 400-700, latin
plexmono-400.woff2     14,708 B
plexmono-500.woff2     14,888 B
```

`font-display: swap`, so a missing or slow font never blocks render.

### Scale

1.25 ratio on a 16px base. Line-height tightens as size grows; tracking goes negative on
display sizes and positive on small caps.

| Token | Size | Line-height | Tracking | Use |
|---|---:|---:|---:|---|
| `--text-display` | 2rem | 1.15 | −0.02em | View title |
| `--text-h2` | 1.5rem | 1.25 | −0.015em | Section heading |
| `--text-h3` | 1.125rem | 1.35 | −0.01em | Card heading |
| `--text-lead` | 1.0625rem | 1.6 | — | Lead paragraph |
| `--text-body` | 0.9375rem | 1.6 | — | Body, controls |
| `--text-sm` | 0.875rem | 1.5 | — | Table cells, hints |
| `--text-xs` | 0.75rem | 1.4 | +0.04em | Labels, overlines |

**Before:** ad-hoc `em`/`rem` values scattered through the file, no line-height or
letter-spacing system, `-apple-system` for every role.

Every numeral carries `font-variant-numeric: tabular-nums` so columns align.

---

## 2. Colour

Warm-tinted neutrals rather than pure grey, and an indigo primary rather than the default
`#2451c9` blue — the two cheapest ways to stop looking bootstrapped.

| Role | Light | Dark |
|---|---|---|
| `--bg` | `#f7f7f5` | `#0e0e10` |
| `--surface` | `#ffffff` | `#17171a` |
| `--surface-2` | `#f2f2ef` | `#1e1e22` |
| `--surface-3` | `#ebebe7` | `#26262b` |
| `--border` | `#e4e4df` | `#2a2a2f` |
| `--border-strong` | `#cfcfc8` | `#3a3a41` |
| `--text` | `#17171a` | `#f0f0ee` |
| `--text-2` | `#4a4a52` | `#b4b4bd` |
| `--muted` | `#6e6e78` | `#86868f` |
| `--primary` | `#4f39cf` | `#8b7af0` |
| `--ok` / `--warn` / `--err` | `#157a41` / `#a45c00` / `#b3221a` | `#46c97a` / `#e0a244` / `#ff6f63` |

### Measured contrast

Computed, not eyeballed. All pass WCAG AA for their role.

| Pair | Light | Dark |
|---|---:|---:|
| text on surface | 17.89:1 | 15.68:1 |
| text-2 on surface | 8.78:1 | 8.69:1 |
| muted on surface | 5.04:1 | 4.96:1 |
| muted on bg | 4.70:1 | 5.34:1 |
| primary on surface | 7.45:1 | 5.23:1 |
| ok / warn / err on surface | 5.40 / 5.11 / 6.64 | 8.43 / 8.03 / 6.56 |

### Chart palette (separate, separately validated)

`--viz-blue` `--viz-orange` `--viz-red` `--viz-neutral` are **not** UI colours and are
validated with the data-viz palette validator against the real card surface in both
modes. Every adjacent pair clears the CVD, normal-vision and contrast gates, with one
documented exception:

> `--viz-neutral` ↔ `--viz-red` measures **ΔE 3.9 (protan) on the dark surface** — below
> the gate. The neutral is the prescribed diverging midpoint and cannot take chroma, so
> the direction-consistency chart **direct-labels every segment with its count**. Identity
> rests on the number, not the hue. See `charts.js`.

---

## 3. Spacing

`--space-1…8` = `4 · 8 · 12 · 16 · 24 · 32 · 48 · 64px`.

| Context | Value |
|---|---|
| Card padding | 16px (`<md`) → 24px → 28px (`≥xl`) |
| Page gutter | 16px (`<md`) → 24px → 48px (`≥xl`) |
| Card gap | 16px |
| Field gap | 16px |
| Content max-width | 1360px; prose capped at `68ch` |

**Before:** a 0.25rem-based ramp mixed with inline `style="width:4em"` overrides. Those
inline styles are gone.

---

## 4. Radii and elevation

`--radius-sm: 8px` (buttons, inputs, badges, chips) · `--radius-md: 12px` (cards, panels,
drawer, image frames) · `--radius-full: 999px` (pills, progress bars).
**Before:** an inconsistent 5 / 6 / 9 / 10 / 14px.

Elevation is layered and tied to interaction, never decorative. Borders remain the
primary separator; shadow is secondary.

| Token | Use |
|---|---|
| `--elev-1` | Cards at rest |
| `--elev-2` | Hover, sticky header, primary card |
| `--elev-3` | Run panel |
| `--elev-4` | Drawer |

Dark mode raises the alpha and adds `--inner-hi`, a 1px top inner highlight — shadow
alone does not read against a dark surface, so the highlight carries the edge instead.

---

## 5. Component states

Applied to every interactive element, not just `<button>`.

| Element | hover | active | focus-visible | disabled | loading | error |
|---|---|---|---|---|---|---|
| Button ×4 variants | darker fill + `elev-2` | `translateY(1px)`, darkest fill, no shadow | 2px ring, 2px offset | 45% opacity, no pointer | spinner + `aria-busy`, label kept | — |
| Input / select | `border-strong` → `text-2` | — | primary border + 3px soft ring | `surface-2`, muted text | — | `aria-invalid` + red border + message |
| Checkbox | outline on the box | — | ring | dimmed | — | — |
| Rail item | `surface-2` | — | ring | — | — | — |
| Segmented / chip | 6% ink wash | `aria-pressed` raised chip | ring | dimmed | — | — |
| Table row | `surface-2` | — | ring (actionable) | — | skeleton rows | — |
| Sortable header | text → `--text` | — | ring | — | — | — |
| Filmstrip control | `surface-2` | `aria-current` filled | ring | — | — | — |

Loading keeps the label in place so the button does not resize and shift its neighbours;
`aria-busy` carries the state to assistive tech. Errors are never the red border alone —
`aria-invalid` exposes them programmatically and a message states what is wrong.

**Skeletons** (`.skeleton`) replace bare "Loading…" text wherever the result's shape is
known, so the layout does not jump when data lands.

**Motion:** `--dur-fast 120ms` (colour, border) · `--dur-mid 180ms` (elevation, transform)
· `--dur-slow 240ms` (drawer, progress). All of it collapses to ~0 under
`prefers-reduced-motion: reduce`.

---

## 6. Layout and responsiveness

Breakpoints: **sm 480 · md 768 · lg 1024 · xl 1280**.

| Width | Behaviour |
|---|---|
| ≥ xl | 48px gutters, 28px card padding |
| ≥ lg | Two-column shell, `264px` rail |
| < lg | Rail becomes a horizontally scrollable tab strip; `.row` stacks |
| < md | Comparison stacks; **Results table becomes one card per row**; every interactive element ≥ 44px; `.kv` stacks; drawer goes full-screen |
| < sm | Header meta hidden, field rows stack |

The mobile table is not a horizontal scroller: `thead` is visually hidden and each `<td>`
carries `data-label`, rendered as the field name beside its value.

### Touch targets

`--tap: 44px` is applied to `button`, `input`, `select`, `summary`, `.list li` and rail
items. `button.small` reduces padding and type size only — never the hit area.
Segmented and filmstrip controls sit at 34/36px for pointer input and are raised to 44px
under `md`.

**Verified**, not assumed: with the `max-width: 767px` block active, all 31 rendered
interactive elements measured ≥ 44px via `getBoundingClientRect()`.

---

## 7. CTA hierarchy

One filled primary action per view; everything else demotes.

| View | Primary |
|---|---|
| Dataset | — (a reading view) |
| Models | Add model |
| Evaluate | Start evaluation |
| Collect | Start collection |
| Results | — (a reading view) |
| Analyze | Run analysis |

`secondary` (outlined) for supporting actions, `ghost` for tertiary, `danger` reserved for
cancel/destructive. The view's primary card also carries a tinted border and `--elev-2`.

---

## 8. Accessibility commitments

A benchmark measuring accessibility settings has no business failing these.

- One focus treatment for everything keyboard-reachable; `outline` is never removed
  without a replacement ring.
- Status is never colour alone: badges carry a dot **and** a text label, chart
  significance is filled-vs-hollow, underpowered rows carry `†`, stacked segments are
  direct-labelled.
- `aria-current` (rail, filmstrip), `aria-live="polite"` (run status), `aria-busy`
  (loading buttons), `aria-invalid` (fields), `role="alert"` (errors).
- Usable at 200% zoom and 400px width.
- `prefers-reduced-motion: reduce` collapses every animation and transition.
