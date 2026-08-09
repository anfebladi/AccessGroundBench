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
cp .env.example .env
# edit .env with VLM_MODEL and the provider key it requires
```

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
dataset/      Local captures, labels, manifests, and archived results
tests/        Unit tests
outputs/      Standalone utility output
```

Captures under `dataset/images/`, `dataset/raw_xml/`, and `dataset/labels/` are
generated locally by the collection workflow; they are not gitignored.

## Common workflow

```bash
agb collect
agb evaluate
agb analyze
agb analyze --csv dataset/evaluation_results_MODEL.csv
agb rescore --csv dataset/evaluation_results_MODEL.csv --check
```

Collection can be checked without an emulator with `agb collect --dry-run`.
For the capture reference and recovery options, see
[`docs/collection.md`](docs/collection.md); for a live operator checklist, see
[`docs/runbooks/collection.md`](docs/runbooks/collection.md). For every command
and option, see [`docs/cli-reference.md`](docs/cli-reference.md).

## Documentation

- [`docs/setup.md`](docs/setup.md) — installation, environment variables,
  emulator preparation, and coordinate-space guidance
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
