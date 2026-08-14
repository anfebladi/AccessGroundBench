# `agb` CLI reference

The installed `agb` command exposes collection, evaluation, analysis, and
offline-maintenance workflows. Paths are relative to the current working
directory unless absolute. Run `agb <command> --help` for argparse help.

```text
agb {collect,evaluate,analyze,canonicalize,rescore,profile,capture,extract}
```

## `agb collect`

For emulator prerequisites, profile sequence, artifact validation, and recovery
workflow, see the [Android collection guide](collection.md).

```text
agb collect [--dry-run] [--screens SCREEN [SCREEN ...]] [--rebuild-manifest]
```

**Purpose.** Capture the configured screens under each accessibility profile,
extract labels, and write `experiment/dataset/collection_manifest.json`.

**Use when.** Run a live collection with an attached emulator, preview the
planned sequence, or reconstruct a manifest from assets already on disk.

**Inputs and outputs.** Live mode uses the emulator/ADB and writes
`experiment/dataset/images/{screen}_{profile}.png`,
`experiment/dataset/raw_xml/{screen}_{profile}.xml`,
`experiment/dataset/labels/{screen}_{profile}.json`, and
`experiment/dataset/collection_manifest.json`. `--rebuild-manifest` reads those existing
directories and rewrites the manifest without captures. A rebuild with
`--screens` updates that subset, carries unselected screen records forward,
and overwrites the manifest file; omit it to rebuild all screens.

**Effects and safety.** Live collection changes emulator display settings,
navigates screens, captures assets, and resets profiles after each screen.
`--dry-run` makes no ADB or emulator calls and writes no captures or manifest,
though it may create the required dataset directories. Rebuilding is offline
but replaces the manifest file.

**Flags.** `--screens` replaces the default complete built-in screen list.

```bash
agb collect --dry-run
agb collect --screens settings_main contacts dialer
agb collect --rebuild-manifest
agb collect --rebuild-manifest --screens settings_main
```

## `agb evaluate`

```text
agb evaluate [--fresh] [--force-unlock]
```

**Purpose.** Call the configured VLM APIs for targets in the input captures and
write one result file per configured model and prompt mode at
`experiment/outputs/evaluations/<model>_<vision|tree>.csv`.

**Use when.** Evaluate new captures or continue an interrupted evaluation.

**Inputs and outputs.** Inputs are baseline labels and captured images under
`dataset/` (plus the configured model/API credentials and evaluation environment). Results are
CSV rows containing each model response and score.

**Effects and safety.** This command calls external VLM APIs; it does not
navigate or capture the emulator. Normal runs resume existing rows. Per-CSV
locks prevent concurrent evaluators from appending duplicate rows. A run that
fails before producing data may leave no result file.

**Flags.** `--fresh` discards existing rows and restarts. `--force-unlock`
removes a stale per-CSV `.lock` file before starting.

```bash
agb evaluate
agb evaluate --fresh
agb evaluate --force-unlock
```

## `agb analyze`

```text
agb analyze [--data-dir PATH] [--csv PATH]
            [--permutations INTEGER] [--seed INTEGER]
            [--compare-a PATH] [--compare-b PATH]
            [--label-changed {exclude,unreachable,reachable}]
            [--mode {vision,tree}]
            [--sample {full,primary,precautionary,uniform,all}]
```

**Purpose.** Read evaluation CSVs, compute reachability and statistical
reports, and serialize analysis tables.

**Use when.** Summarize all matching model CSVs, analyze one CSV, or compare a
vision-only file with a with-tree file.

**Inputs and outputs.** `--csv` selects one result file; otherwise discovery
uses evaluation results under `experiment/outputs/evaluations/` for `--mode` (`vision` by
default). Reports are written under `experiment/outputs/analysis/<mode>_<sample>/`.
Paired comparisons are written under `experiment/outputs/analysis/comparisons/`.

**Effects and safety.** Analysis reads and reclassifies data in memory; it
does not mutate source evaluation CSVs. Report files are rewritten. The
`--compare-a` and `--compare-b` options must be supplied together; comparison
uses `primary` when `--sample all` is selected.

**Flags.** `--permutations` defaults to `20000`; `--seed` defaults to `0`.
`--label-changed` defaults to `unreachable`; `--sample` defaults to `all`.

```bash
agb analyze
agb analyze --data-dir experiment/archive/experiment_2 --mode vision
agb analyze --csv experiment/outputs/evaluations/MODEL_vision.csv --sample primary
agb analyze --compare-a a.csv --compare-b b.csv
```

## `agb canonicalize`

```text
agb canonicalize [--csv PATH [PATH ...]]
```

**Purpose.** Repair evaluation CSVs to one canonical row per expected
`(screen, target_text, profile)` key.

**Use when.** Repair legacy files, files with duplicate rows, or files made
stale by a changed target set. This is also useful after a lock was deleted
mid-run.

**Inputs and outputs.** Offline, it reads baseline labels to derive the
expected key order, removes stale-target, `api_error`, and duplicate rows,
sorts canonically, and rewrites each selected CSV. A `.csv.bak` backup is
created before each rewrite. By default it processes all
evaluation result files under `experiment/outputs/evaluations/`; `--csv` selects one or more.

**Effects and safety.** No API calls or emulator calls are made. Per-CSV locks
guard the rewrite; a held lock is reported as a problem. Rewriting replaces
the CSV, while the `.bak` copy preserves the prior bytes.

```bash
agb canonicalize
agb canonicalize --csv experiment/outputs/evaluations/MODEL_vision.csv
```

## `agb rescore`

```text
agb rescore --csv PATH [--coord-space {pixel,norm1000}] [--check]
```

**Purpose.** Recompute stored coordinate predictions and hit scores under a
coordinate convention.

**Use when.** Use `--check` to compare conventions first, then use
`--coord-space` to apply the chosen convention.

**Inputs and outputs.** `--csv` is the required evaluation CSV. `--check`
prints scored rows, hits, and accuracy for both conventions without writing.
Applying `--coord-space` rewrites the CSV and creates `PATH.csv.bak`.

**Effects and safety.** `--check` is read-only. Apply mode overwrites the CSV
after making the backup; rerun `agb analyze --csv PATH` afterward.

**Flags.** Either `--check` or `--coord-space` is required; `--coord-space`
accepts `pixel` or `norm1000`.

```bash
agb rescore --csv experiment/outputs/evaluations/MODEL_vision.csv --check
agb rescore --csv experiment/outputs/evaluations/MODEL_vision.csv --coord-space norm1000
```

## `agb profile`

```text
agb profile PROFILE|reset
```

**Purpose.** Apply one named accessibility profile to the active Android
device, or reset all profile vectors to baseline.

**Use when.** Adjust font scale, density, RTL, or color-vision settings before
a manual capture or diagnostic check.

**Inputs and outputs.** The positional argument is a profile name listed by
`agb profile --help`, or the literal `reset`. The command applies settings via
ADB, waits for Android to settle, and verifies them; `reset` restores baseline
vectors.

**Effects and safety.** Requires a connected Android device and changes its
settings. Failed application attempts trigger an emergency reset.

```bash
agb profile elder_combo_max
agb profile reset
```

## `agb capture`

```text
agb capture [output_name]
```

**Purpose.** Capture one synchronized Android screenshot and UI hierarchy.

**Use when.** Collect a standalone pair of assets outside the full collection
workflow.

**Inputs and outputs.** The optional `output_name` is the file stem. With no
name, the pipeline uses `capture_YYYYMMDD_HHMMSS` (UTC). It writes
`outputs/captures/<stem>.png` and `outputs/captures/<stem>.xml` by default.

**Effects and safety.** Requires ADB and an attached device; captures and pulls
files, crops system bars, and cleans temporary device files.

```bash
agb capture
agb capture my_capture
```

## `agb extract`

```text
agb extract XML_PATH [--output PATH] [--y-offset INTEGER] [--bottom-crop INTEGER]
```

**Purpose.** Parse one Android UI hierarchy XML and produce normalized
bounding-box labels.

**Use when.** Convert a captured XML to labels, optionally matching screenshot
cropping offsets.

**Inputs and outputs.** `XML_PATH` is required. The JSON output defaults to the
same directory and filename stem as the XML (for example,
`outputs/captures/capture.xml` becomes `outputs/captures/capture.json`); `--output` selects a
different path and overwrites it if present. `--y-offset` and `--bottom-crop`
default to `0` pixels.

**Effects and safety.** Offline: reads XML and writes JSON; it does not call
ADB. Invalid or missing XML is an error.

```bash
agb extract outputs/captures/my_capture.xml
agb extract outputs/captures/my_capture.xml --output outputs/captures/my_capture.json --y-offset 0 --bottom-crop 0
```
