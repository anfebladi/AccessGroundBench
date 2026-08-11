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

Self-hosted, two roles. Headings and body both run on Inter -- one modern sans instead of
a serif-for-headings/sans-for-body split, to match the reference sites this pass was built
against (Coursera, EventAura-style landing pages). Numerals and code stay on a mono face:
a UI sans doesn't give you tabular figures.

| Role | Token | Family | Used for |
|---|---|---|---|
| Display / UI | `--font-display`, `--font-ui` | Inter (variable 400–700) | Headings, lead paragraphs, pane titles, body, controls |
| Mono | `--font-mono` | IBM Plex Mono 400/500 | All numerals, code, table heads, status labels |

Bundled files (~76 KB total), both families SIL OFL 1.1 — the licence ships beside them
in `static/FONTS-LICENSE.txt` because the licence requires it:

```
inter.woff2            48,256 B   variable 400-700, latin
plexmono-400.woff2     14,708 B
plexmono-500.woff2     14,888 B
```

`font-display: swap`, so a missing or slow font never blocks render.

### Scale

1.25 ratio on a 17px base (up from 16px — sized up a step across every role, not just
headings). Line-height tightens as size grows; tracking goes negative on display sizes and
positive on small caps.

| Token | Size | Line-height | Tracking | Use |
|---|---:|---:|---:|---|
| `--text-display` | 2.25rem | 1.15 | −0.02em | View title |
| `--text-h2` | 1.625rem | 1.25 | −0.015em | Section heading |
| `--text-h3` | 1.1875rem | 1.35 | −0.01em | Card heading |
| `--text-lead` | 1.125rem | 1.6 | — | Lead paragraph |
| `--text-body` | 1.0625rem | 1.6 | — | Body, controls |
| `--text-sm` | 0.9375rem | 1.5 | — | Table cells, hints |
| `--text-xs` | 0.8125rem | 1.4 | +0.04em | Labels, overlines |

**Before:** ad-hoc `em`/`rem` values scattered through the file, no line-height or
letter-spacing system, `-apple-system` for every role.

Every numeral carries `font-variant-numeric: tabular-nums` so columns align.

---

## 2. Colour

A six-stop navy-to-white blue ramp (`#011f4b · #03396c · #005b96 · #6497b1 · #b3cde0 ·
#ffffff`). Blue is an **accent, not a surface colour** — the page canvas, cards and header
are white/near-white, and saturated blue is reserved for things that ask to be touched:
buttons, the active step, a link, the logo chip. A page that tints every surface blue reads
as heavier and less legible, not more branded — see the reference sites this pass was
built against.

Light-only; there is no dark variant (see [§0 below](#0-why-no-dark-mode)).

| Role | Value |
|---|---|
| `--bg` | `#ffffff` |
| `--surface` | `#ffffff` |
| `--surface-2` | `color-mix(in srgb, #b3cde0 12%, #ffffff)` |
| `--surface-3` | `color-mix(in srgb, #b3cde0 22%, #ffffff)` |
| `--border` | `color-mix(in srgb, #6497b1 35%, #ffffff)` |
| `--border-strong` | `color-mix(in srgb, #6497b1 70%, #ffffff)` |
| `--text` | `#011f4b` |
| `--text-2` | `#03396c` |
| `--muted` | `#005b96` |
| `--primary` | `#005b96` |
| `--ok` / `--warn` / `--err` | `#3d6b1f` / `#755509` / `#a3301f` (kept outside the brand ramp — status colour, not chrome) |

**Accents**, used sparingly and only for the few things that stay dark regardless of the
rest of the page (pane captions over device screenshots):

| Token | Value | Used for |
|---|---|---|
| `--forest` / `--forest-deep` | `#011f4b` | pane headers over device captures |
| `--chartreuse` | `#b3cde0` | accent text on the dark caption bar |
| `--moss` | `#6497b1` | non-text fills only — data bars, bullets |
| `--sage` | `#b3cde0` | (unused now that header/rail chrome follows `--surface`/`--primary`) |

`--moss` sits at 3.2:1 on `--surface` and is deliberately **never** used for text; it
clears the 3:1 threshold that applies to UI components and data marks.

**One rule drives every text pairing:** a light surface always carries dark-navy text, a
dark surface always carries white or pale-blue text — never the reverse.

### Measured contrast

Computed, not eyeballed. All pass WCAG AA for their role.

| Pair | Ratio |
|---|---:|
| text on surface | 16.5:1 |
| text-2 on surface | 11.6:1 |
| muted on surface | 7.1:1 |
| primary-fg on primary (button) | 7.1:1 |
| header text on header bg | 16.2:1 |
| active rail item (tint) | 6.1:1 |
| brand-mark chip | 7.2:1 |

### 0. Why no dark mode

Every reference for this design (Coursera, EventAura, the Greenfly-style card layout) is a
white, light-only page with blue confined to nav/buttons/accents. Following the OS into a
dark theme would reintroduce exactly the wall-to-wall blue this palette pass removed, on a
schedule the user doesn't control. `color-scheme: light` in the root token block stops
native form controls (scrollbars, checkboxes) from rendering dark on their own even when
the OS prefers it.

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

`--inner-hi` is reserved for a future dark surface — shadow alone won't read there, so a
1px top inner highlight would carry the edge instead. Unused while the UI is light-only.

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
