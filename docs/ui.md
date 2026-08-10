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

If `fastapi`/`uvicorn` are not installed, `agb ui` prints the install command
above and exits; every other `agb` command is unaffected.

## Front end

Plain HTML, CSS and ES modules, served straight out of `src/webui/static/`.
**There is no build step, no `package.json`, and no Node toolchain** -- the UI
ships as package data inside an optional `pip` extra, so a bundler would put a
Node install between a contributor and `uv sync --extra ui`. Charts are
hand-written inline SVG for the same reason. Keep new files flat in `static/` --
the `package-data` glob in `pyproject.toml` is `static/*` and does not recurse.

Every colour, size, radius, shadow and duration is a CSS custom property defined
once at the top of `style.css`, which is organised into layers (`FONTS → TOKENS →
BASE → LAYOUT → COMPONENTS → UTILITIES → RESPONSIVE`) in place of a preprocessor.
Dark mode is a token swap, not a second stylesheet. The full token reference,
measured contrast ratios, the component state matrix and the responsive rules are
in [`docs/ui-design-system.md`](ui-design-system.md).

Two typefaces are bundled (~162 KB) rather than loaded from a CDN, because the
server binds localhost and must work offline: **Newsreader** for headings and
lead prose and **IBM Plex Mono** for numerals, code and data labels, with the
system sans for controls. Both are SIL OFL 1.1 and their licence ships beside
them in `static/FONTS-LICENSE.txt`, which the licence requires.

## Steps

The six steps are ordered the way the pipeline runs, and the left rail carries
a live status for each: how many screens the active dataset has, how many
models are configured, how many queries an evaluation still has to make.

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
`outputs/evaluations/<model>/<vision|tree>/results.csv`
exactly as `agb evaluate` would leave them, including the append/resume/lock
semantics documented in the [evaluation runbook](runbooks/evaluation.md).

**Results.** One sortable row per result file: accuracy over co-present
targets, and the rows excluded from that denominator by status. Column
headings are the readable names; the underlying CSV status is in each one's
tooltip. Because vision and tree results are never pooled, a mode filter is
offered whenever both are present.

The miss inspector steps through every `co_present` miss for a model -- with
the screenshot, ground-truth box, predicted point, parse method and raw reply
shown together -- driven by the arrow keys, `Escape`, or the filmstrip.

**Analyze.** Runs `agb analyze` and charts reachability (with Wilson
intervals), pooled permutation (primary), per-model McNemar (secondary), and
direction consistency. Every chart keeps its table underneath it: the chart is
the scan layer, the numbers stay the source of truth.

Ceiling/floor-flagged rows are marked with the same caution as
[`docs/methods.md`](methods.md) -- an underpowered null is not evidence of
resilience -- and the survivorship caveat on the co-present set is printed
above the results, not left to whoever opens a table. Significance is shown by
a filled versus hollow marker and underpowered rows by a dagger, so neither
depends on colour alone. Vision and tree arms are analysed one at a time and
are never pooled.

**Analysis from the UI never writes into a dataset.** Results go to
`outputs/analysis/<mode>_<sample>/`, and the path is shown above the
charts. This is not cosmetic: `agb analyze` names its outputs after the
analysis rather than the run, so running it twice with different `--sample`
values overwrites the earlier tables in place. From a terminal that is a
deliberate act; from the browser it would be one click on the page you land
on, quietly narrowing the tables committed alongside `dataset/` to whichever
sample was selected. Mode and sample are part of the directory name so a
vision run and a tree run cannot overwrite each other either. Archived
datasets can be analysed freely, because nothing is written inside them.

Analysis output is written under `outputs/analysis/<mode>_<sample>/`; prompt-arm
comparisons use `outputs/analysis/comparisons/`. Historical generated outputs
are kept under `outputs/archives/`; archived source captures remain in
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
- `dataset/experiment_1`, `dataset/experiment_2` -- archived prior runs,
  shown **read-only**: Evaluate and Collect refuse to target them (see the
  archive warning in [`README.md`](../README.md) and
  `dataset/experiment_2/README.md`).
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
  charts read the same `*_results.csv` files `agb analyze` writes and compute
  nothing of their own.
- **Modify a dataset it is reading.** Collect writes only to
  `datasets/<name>/`, analysis writes only to `outputs/analysis/`, and Evaluate
  appends to its own result CSV. Nothing in the UI rewrites a dataset's
  captures, labels, or committed analysis tables.
- **Run over a network.** Local-only, by design (see [Launch](#install-and-launch)).
- **Require Node.** See [Front end](#front-end). If you find yourself wanting a
  bundler, weigh it against the fact that this is an optional extra of a
  deliberately dependency-light benchmark.
