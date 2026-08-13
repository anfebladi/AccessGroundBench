# Web UI

`agb ui` is a local, browser-based front end for the same three commands
documented in the [CLI reference](cli-reference.md): `collect`, `evaluate`,
and `analyze`. It does not replace them or add a second pipeline -- every
button click runs the same `agb` subcommand a terminal would, against the
same dataset layout, writing the same files in the same format. The
equivalent command is shown before every run so it stays reproducible outside
the browser.

Intended audience: someone evaluating their own model or app screens against
this benchmark without first learning its env-var vocabulary.

## Install and launch

The UI is an optional extra so the core benchmark stays dependency-light:

```bash
uv sync --extra ui
agb ui
# agb ui --port 8081   # if 8080 is taken
```

Opens `http://127.0.0.1:8080`. The server binds `127.0.0.1` only -- this is
not configurable -- because provider API keys entered in the browser are held
in the server process's memory (see [Keys](#keys) below) and must never be
reachable from another machine.

One `agb ui` process starts both services: the FastAPI API on `--api-port 8081`
and the Vite development server on `--port 8080`. The Vite server proxies
`/api` requests to the API.

If `fastapi`/`uvicorn` are not installed, `agb ui` prints the install command
above and exits. If frontend dependencies are missing, it prints the one-time
Node install command and exits; every other `agb` command is unaffected.

## Front end

The browser UI is a React + Vite application. Its source, package manifest and
build configuration live in `src/webui/frontend/` (`src/webui/frontend/src/`,
`src/webui/frontend/package.json`, and `src/webui/frontend/vite.config.ts`).
`agb ui` runs the FastAPI API and Vite UI together; Vite serves the React source
locally and proxies API calls to the API port. Node is required while the local
UI is running.

The UI is implemented entirely with typed React components and hooks. The
application shell owns routing, shared dataset/provider/model state, and
cross-view refreshes; each of the seven workflow views owns its forms and
loading/error states. Run polling, comparison canvases, charts, keyboard
navigation, drawers, and exports are React-managed effects and refs. The
frontend now uses a feature-based layout; the former `src/views/` and
`src/reporting/` trees are removed. Keep the current route hashes, DOM hooks,
API payloads, local-storage formats, and visual tokens stable when changing a
feature.

On desktop, the shell's workflow rail may be collapsed to an icon-only column and
the preference persists in browser storage (`agb.sidebar.collapsed`). Collapsed
links retain their route names through accessible labels and tooltips; the mobile
Sheet menu remains independent and always shows the expanded labels. Shared data
requests use shape-matched skeletons for predictable content (metadata, cards,
tables, charts, and image frames), while long-running jobs keep their live status
and progress indicators. Loading placeholders resolve to the normal empty or error
state rather than masking a completed request.

### Front-end architecture

`src/webui/frontend/src/main.tsx` is the bootstrap and public export entry
point. Composition lives in `app/App.tsx`, which connects shared data
hooks to the keep-mounted page outlet. The shell is split into `AppShell`,
`TopBar`, `Sidebar`, `CommandPalette`, `PageOutlet`, and `ErrorBoundary`;
`app/navigation.ts` defines tab order, route hashes, route groups, and palette
item types. The seven workflow areas live in
`src/features/{dataset,models,evaluate,collect,compare,results,analyze}/`.
Cross-feature workflow support is shared under `src/features/shared/`, while
shell components, UI primitives, hooks, utilities, and global styles remain in
their respective shared `components/`, `app/`, `lib/`, and `styles/` areas.

Pages remain mounted while inactive and are toggled with `hidden`. This keeps
in-progress view state and preserves the existing hash and DOM contracts:
`dataset`, `models`, `evaluate`, `collect`, `compare`, `results`, and `analyze`,
including numeric shortcuts, `data-tab`, IDs, and ARIA hooks. Shared provider
refreshes are owned by the app data hook, so Models changes update the sidebar
and other views without a reload.

If `src/webui/frontend/node_modules/` is absent, install the frontend
dependencies once with:

```bash
cd src/webui/frontend
npm ci
```

The normal workflow is then `agb ui`. The optional `npm run build` command runs
the TypeScript check and Vite production build for a local compile check. Its
output is written to the ignored `src/webui/frontend/dist/` directory; no
static bundle is committed or served by the Python package. Use `npm run dev`
only when working on the frontend outside the combined launcher. For frontend
changes, run the unit baseline and production build from
`src/webui/frontend/`:

```bash
npm run test       # Vitest unit test suite
npm run build      # TypeScript + Vite build
npm run test:e2e   # Playwright UI and responsive snapshot baseline
```

The repository's Python test suite remains the backend/integration regression check:

```bash
uv run python -m unittest discover -s tests -p "test_*.py"
```

Every colour, size, radius, shadow and duration is a CSS custom property defined
in the authored token/base styles loaded by `style.css`; `styles/tokens.css` and
`styles/globals.css` provide shared entry points. Tailwind CSS v4 is the
component and layout styling authority, including feature and shell composition.
Authored CSS is intentionally limited to bundled fonts, design tokens, base/reset
rules, global focus behavior, keyframes, and unavoidable specialized SVG/export
rules. CSS Modules are not part of the frontend styling contract.
The page canvas is light-only by design -- the OS dark-mode setting is not
followed for the *page*, so it never lands on a heavier, bluer theme than the
one it was designed against. Screenshots, charts and the Compare stage sit on a
fixed dark panel regardless of OS preference, which is a different thing: an
intentional design element on specific data surfaces, not a page-wide theme.
The full token reference, measured contrast ratios, the component state matrix
and the responsive rules are in
[`docs/ui-design-system.md`](ui-design-system.md).

One typeface family is bundled rather than loaded from a CDN, because the
server binds localhost and must work offline: **Geist** for everything but
numerals, code and data labels, which stay on **Geist Mono** for tabular
figures. The source font files live in `src/webui/frontend/public/` and are
served by the local Vite frontend; both families remain SIL OFL 1.1. Icons are inline SVG for the same
offline-first reason -- no icon font, no CDN. Preserve the CSS custom-property
design tokens in `src/webui/frontend/src/style.css` and the shared files under
`src/webui/frontend/src/styles/` when changing the visual system;
`src/webui/frontend/dist/` is disposable local build output.

## Steps

The seven steps are ordered the way the pipeline runs, and the left rail
carries a live status for each: how many screens the active dataset has, how
many models are configured, how many queries an evaluation still has to make.

**Dataset.** Picks the active dataset from a dropdown (see
[Datasets](#datasets)), shows its screen/target/capture counts, and surfaces
`collection_manifest.json` warnings -- content drift, colour-contamination
flags -- before you read any numbers reported against it. The screen browser
puts the baseline capture **side by side** with one accessibility profile,
captioned with each one's pixel dimensions (they differ with display density)
and with the ground-truth boxes drawn over both. Baseline targets that the
profile has evicted are outlined separately on the baseline pane, so the
reachability loss that drives the headline result is visible on the screen
itself rather than only in a table.

**Models.** Configure a model, check that its provider is set up, and run a
**Test model** query: one real call against one target, with the prediction
drawn against the ground-truth box and the detected coordinate convention
(pixel vs. 0-1000) reported. This is the fastest way to catch a bad key,
wrong coordinate space, or malformed model id before spending a full ~1000
paid queries finding out. See [Bring your own model](#bring-your-own-model).

**Evaluate.** Configure and launch `agb evaluate` against the selected
dataset. Before starting, a preflight panel reports the planned call count,
how many are already done (resume status), and whether a stale lock is
present. The stale-lock override only appears when a lock actually exists,
since it is never the right thing to tick otherwise.

While the run is going, a determinate progress bar reports queries completed
against the planned total, with elapsed time, an ETA, and a live tally by
outcome -- so an `api_error` streak is visible as it happens rather than after
the fact. Progress is counted on the client from the run's own stdout, which
prints one line per query; there is no second source of truth about how far
along a run is. The raw log is one disclosure away, and stops auto-scrolling
as soon as you scroll back through it. Results land in
`experiment/outputs/<dataset>/evaluations/<model>_<vision|tree>.csv`
exactly as `agb evaluate` would leave them, including the append/resume/lock
semantics documented in the [evaluation runbook](runbooks/evaluation.md).

**Compare.** The benchmark's headline question, answered without running a
full analysis: pick one evaluated model, and see its accuracy on the baseline
layout against each accessibility profile immediately -- a chart, a delta per
profile, and a three-state significance readout (Significant / No
significant change / **Underpowered -- can't tell**). The third state
exists because a plain yes/no would misrepresent most of this benchmark's own
data: a model sitting near ceiling baseline accuracy with only a handful of
discordant pairs is untestable, not resilient, and the UI must not imply
otherwise (see [`docs/methods.md`](methods.md) and `src/webui/backend/compare.py`'s
module docstring). The Holm-Bonferroni correction runs across every model
evaluated on the dataset, not just the one being displayed -- narrowing the
family to one model's own profiles would let the same p-value read as
significant here and not-significant in `agb analyze`'s canonical tables,
which is exactly the defect this endpoint is built to avoid.

**Results.** A chart of overall accuracy across every evaluated model, then
one sortable row per result file: accuracy over co-present targets, and the
rows excluded from that denominator by status. A "vs. baseline" column shows
whether a model's blended accuracy is hiding degradation relative to its own
clean baseline -- worded ("X pts lower/higher"), not a bare sign, since a
positive delta means accuracy *dropped* under this codebase's paired-difference
convention and a "+" prefix would read backwards. Column headings are the
readable names; the underlying CSV status is in each one's tooltip. Because
vision and tree results are never pooled, a mode filter is offered whenever
both are present.

The miss inspector steps through every `co_present` miss for a model -- with
the screenshot, ground-truth box, predicted point, parse method and raw reply
shown together -- driven by the arrow keys, `Escape`, or the filmstrip.

**Analyze.** Shows whatever the current mode/sample combination already has
on disk **on arrival**, with no run required -- if `agb analyze` (or an
earlier browser run) already wrote tables to
`experiment/outputs/<dataset>/analysis/<mode>_<sample>/`, they render immediately.
Changing the Sample or Prompt mode selector reloads whatever exists for that
combination the same way; the form below is "re-run with new parameters," not
a gate you have to pass to see anything. Charts reachability (with Wilson
intervals), pooled permutation (primary), per-model McNemar (secondary), and
direction consistency. Every chart keeps its table underneath it: the chart is
the scan layer, the numbers stay the source of truth. When "All samples" was
selected at collection time, a sample picker appears above the charts --
each of the four tables carries every named sample's rows in one CSV, and a
chart built from all of them at once would repeat every profile once per
sample, so exactly one sample is charted at a time.

Ceiling/floor-flagged rows are marked with the same caution as
[`docs/methods.md`](methods.md) -- an underpowered null is not evidence of
resilience -- and the survivorship caveat on the co-present set is printed
above the results, not left to whoever opens a table. Significance is shown by
a filled versus hollow marker and underpowered rows by a dagger, so neither
depends on colour alone. Vision and tree arms are analysed one at a time and
are never pooled.

**Analysis from the UI never writes into a dataset.** Results go to
`experiment/outputs/<dataset>/analysis/<mode>_<sample>/`, and the path is shown above the
charts. This is not cosmetic: `agb analyze` names its outputs after the
analysis rather than the run, so running it twice with different `--sample`
values overwrites the earlier tables in place. From a terminal that is a
deliberate act; from the browser it would be one click on the page you land
on, quietly narrowing the tables committed alongside `dataset/` to whichever
sample was selected. Mode and sample are part of the directory name so a
vision run and a tree run cannot overwrite each other either. Archived
datasets can be analysed freely, because nothing is written inside them.

Analysis output is written under `experiment/outputs/<dataset>/analysis/<mode>_<sample>/`; prompt-arm
comparisons use `experiment/outputs/<dataset>/analysis/comparisons/`. Historical generated outputs
are kept under `experiment/outputs/<dataset>/`, one root per dataset; archived source captures remain in
`dataset/experiment_N/`.

Analysis runs in the server process and blocks until it finishes; the form is
locked for the duration. Unlike Evaluate it is not supervised as a subprocess,
so it cannot be cancelled part-way.

**Collect.** Wraps `agb collect`. Always writes to `datasets/<name>/`, never
into the shipped `dataset/` or an archived `dataset/experiment_N/` -- so a
collection run from the UI can never overwrite committed results. An
emulator preflight checks for `adb` and an authorized device; the manual
prerequisites (Pixel 6 / API 34 / 1080x2400 @ 420 dpi, a signed-in Google
account, Messages/Gmail/Maps opened once) are listed but not verifiable from
here -- see [`docs/collection.md`](collection.md).

## Datasets

A dataset is any directory with `images/` and `labels/` subdirectories -- the
same portable unit `agb analyze --data-dir` already accepts. The dropdown
shows:

- `dataset` -- the shipped benchmark, writable.
- `experiment/archive/experiment_1`, `experiment/archive/experiment_2` -- archived prior runs,
  shown **read-only**: Evaluate and Collect refuse to target them (see the
  archive warning in [`README.md`](../README.md) and
  `experiment/archive/experiment_2/README.md`).
- `datasets/<name>/` -- anything you collect from the UI, or copy in
  yourself, lives here rather than inside the shipped `dataset/`.

## Keys

Two ways to configure a provider, and both work together:

- **`.env`** (existing, documented in [`docs/setup.md`](setup.md)) -- the
  default. The Models tab shows each provider's configured/missing status
  read from the environment.
- **Session key** -- pasted into the Models tab, held only in the running
  server process's memory, injected into that provider's env var for
  subprocess runs launched afterward. Never written to disk, never echoed
  back to the browser, gone when the server stops.

A session key overrides `.env` for that provider for the life of the server
process.

## Bring your own model

The underlying call path already accepts any LiteLLM-supported model string,
including an arbitrary `openai_compatible/<model>` gateway -- no code change
needed for most models. Three things commonly go wrong for an unregistered
model, and the **Test model** button on the Models tab is built to catch all
three in one query before a full run:

1. **Wrong coordinate convention.** Only `gemini`, `qwen`, and `glm` are
   recognised as answering on a 0-1000 grid; anything else defaults to pixel
   space. If your model actually answers normalized, it will score near 0%
   silently -- the test flags a detected/expected mismatch explicitly.
2. **Illegal result filename.** Ids containing `:` (common in Ollama tags)
   are sanitized; this was a real crash before Test model existed.
3. **Missing or bad credentials.** Surfaces as one clear error from the test
   call instead of ~1000 silent API failures during a full evaluation.

`COORD_SPACE` is normally one global setting for a whole `agb evaluate`
run, which makes mixing a pixel model and a normalized model in one
`VLM_MODEL` list impossible. The UI sidesteps this by launching one
subprocess per model, so each Evaluate run gets its own coordinate space --
something the bare CLI cannot currently do in a single invocation.

## What the UI does not do

- **Add screens.** Testing your own app's screens still means editing
  `collection/screens.py` (see [`docs/collection.md`](collection.md)); the
  UI's Collect tab captures against the existing screen catalog.
- **Change scoring, statistics, or file formats.** All of that is the same
  code the CLI calls; the UI only supplies a form and a progress view. The
  Analyze/Results charts read the same `*_results.csv` files `agb analyze`
  writes and compute nothing of their own. Compare is the one view that runs
  statistics live rather than reading a finished table, and it does so by
  calling `analysis.reports.grounding.report_per_model` and
  `report_reachability` directly -- the same functions `agb analyze` calls --
  never a JavaScript reimplementation.
- **Modify a dataset it is reading.** Collect writes only to
  `datasets/<name>/`, analysis writes only to `experiment/outputs/<dataset>/analysis/`, and Evaluate
  appends to its own result CSV. Nothing in the UI rewrites a dataset's
  captures, labels, or committed analysis tables.
- **Run over a network.** Local-only, by design (see [Launch](#install-and-launch)).
- **Require Node.** See [Front end](#front-end). Node and the frontend
  dependencies are required at runtime for the local Vite UI.
