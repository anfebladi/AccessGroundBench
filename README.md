# AccessGroundBench

AccessGroundBench measures how Android accessibility layout changes affect a
vision-language model's ability to locate UI text on screen. The current
collection uses large-font, display-zoom, combined, and deuteranomaly profiles;
the RTL arm exists only in the archived experiment.

> **Archive warning:** `dataset/experiment_2/` is a pre-correction run. Its
> headline results must not be cited; see [`dataset/experiment_2/README.md`](dataset/experiment_2/README.md).

The benchmark reports two distinct measurements:

- **Reachability:** whether each baseline target still exists in a modified
  layout, independent of the model.
- **Grounding accuracy:** whether the model locates a target present in both
  layouts. Off-screen targets are not model failures.

The full mathematical treatment is in [`docs/methods.md`](docs/methods.md).

## Requirements

- Python 3.11 or later
- Android Studio/AVD and Android SDK Platform Tools (`adb`)
- CUDA-capable GPU recommended for the optional local Ferret-UI model (CPU
  fallback works but is much slower)

Quickstart:

```bash
uv sync
./scripts/install-agb.sh
cp .env.example .env
# edit .env with VLM_MODEL and the provider key it requires
```

On macOS and Linux, `./scripts/install-agb.sh` installs a project launcher at
`${XDG_BIN_HOME:-$HOME/.local/bin}/agb`. The launcher resolves this clone and
can run bare `agb ...` commands from any directory inside it. The installer
does not edit shell configuration; if the destination directory is not on
`PATH`, add it using the guidance printed by the installer and start a new
shell. On Windows, or when no launcher is installed, use `uv run agb ...`
instead.

See [`docs/setup.md`](docs/setup.md) for provider configuration, emulator
preparation, and coordinate conventions. The collection reference guide is in
[`docs/collection.md`](docs/collection.md); use the [live collection runbook](docs/runbooks/collection.md)
for an operator checklist.
For evaluation using captures that already exist, follow the
[`docs/runbooks/evaluation.md`](docs/runbooks/evaluation.md) runbook.

## Layout

```text
src/          Python package and `agb` command
ferret_ui/    Optional local Ferret-UI server (separate environment)
dataset/      Input captures, labels, and manifests
tests/        Unit tests
outputs/      Evaluation results, analysis reports, and historical outputs
```

Captures under `dataset/images/`, `dataset/raw_xml/`, and `dataset/labels/` are
generated locally by the collection workflow; they are not gitignored.

## Common workflow

```bash
agb collect
agb evaluate
agb analyze
agb analyze --csv outputs/evaluations/MODEL/vision/results.csv
agb rescore --csv outputs/evaluations/MODEL/vision/results.csv --check
```

Evaluation writes one result file per model and prompt mode under
`outputs/evaluations/<model>/<vision|tree>/results.csv`. Analysis reports are
written under `outputs/analysis/<mode>_<sample>/`; comparisons are under
`outputs/analysis/comparisons/`. Historical generated outputs live under
`outputs/archives/`. Archived source captures remain under
`dataset/experiment_N/`.

These commands assume the macOS/Linux launcher setup above. The portable
equivalent is to prefix each command with `uv run` (for example,
`uv run agb collect`); this is also the Windows workflow.

Collection can be checked without an emulator with `agb collect --dry-run`.
For the capture reference and recovery options, see
[`docs/collection.md`](docs/collection.md); for a live operator checklist, see
[`docs/runbooks/collection.md`](docs/runbooks/collection.md). For every command
and option, see [`docs/cli-reference.md`](docs/cli-reference.md).

## Web UI

A local, browser-based alternative to the commands above — evaluate your own
model against the shipped dataset (or one you collect), browse results, and
run the analysis, without memorizing env vars:

```bash
uv sync --extra ui
agb ui
```

Opens on `http://127.0.0.1:8080` (127.0.0.1 only, never exposed to the
network). Every action shows the equivalent `agb` command it ran, and it
writes results in exactly the same place and format the CLI does — the UI is
a front end, not a second pipeline. See [`docs/ui.md`](docs/ui.md).

## Web UI

A local, browser-based alternative to the commands above — evaluate your own
model against the shipped dataset (or one you collect), browse results, and
run the analysis, without memorizing env vars:

```bash
uv sync --extra ui
agb ui
```

Opens on `http://127.0.0.1:8080` (127.0.0.1 only, never exposed to the
network). Every action shows the equivalent `agb` command it ran, and it
writes results in exactly the same place and format the CLI does — the UI is
a front end, not a second pipeline. See [`docs/ui.md`](docs/ui.md).

## Documentation

- [`docs/setup.md`](docs/setup.md) — installation, environment variables,
  emulator preparation, and coordinate-space guidance
- [`docs/ui.md`](docs/ui.md) — local web UI: install, tour, dataset picker,
  bring-your-own-model, and how it maps to the CLI
- [`docs/cli-reference.md`](docs/cli-reference.md) — complete `agb` command
  reference
- [`docs/collection.md`](docs/collection.md) — Android emulator collection
  reference: workflow, artifacts, validation, and recovery
- [`docs/runbooks/collection.md`](docs/runbooks/collection.md) — live collection
  operator checklist and stop/recovery actions
- [`docs/runbooks/evaluation.md`](docs/runbooks/evaluation.md) — evaluation of
  existing captures, prompt modes, coordinate checks, and reporting
- [`docs/ferret-ui.md`](docs/ferret-ui.md) — optional local Ferret-UI server
- [`docs/troubleshooting.md`](docs/troubleshooting.md) — common failures and
  remedies
- [`docs/methods.md`](docs/methods.md) — formulas, estimands, and interpretation limits
