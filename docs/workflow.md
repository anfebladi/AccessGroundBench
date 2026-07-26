# Benchmark workflow

[Back to README](../README.md)

The benchmark runs in three stages: collect data, evaluate VLM grounding, and analyze paired results.

## Stage 1: Collect screenshots and labels

```bash
uv run python -m collection.orchestrator
```

For each of the 13 target screens × 6 profiles, the orchestrator:

- Applies the accessibility profile via ADB settings commands.
- Launches the target app and confirms it is in the foreground.
- Captures the UI hierarchy XML and screenshot.
- Crops system bars (status bar and navigation bar).
- Applies software color filters where required.
- Extracts interactive text elements to a JSON label file.
- Resets the emulator to baseline.

Outputs:

```text
dataset/images/{screen}_{profile}.png
dataset/raw_xml/{screen}_{profile}.xml
dataset/labels/{screen}_{profile}.json
```

Run without an emulator:

```bash
uv run python -m collection.orchestrator --dry-run
```

Collect specific screens only:

```bash
uv run python -m collection.orchestrator --screens settings_main contacts dialer
```

The default target screens are `settings_main`, `settings_display`, `settings_network`, `settings_accessibility`, `contacts`, `dialer`, `messages`, `clock`, `maps`, `play_store`, `gmail`, `youtube`, and `photos`.

## Stage 2: Run VLM evaluation

```bash
uv run python -m vlm_eval.cli
```

The evaluator:

1. Discovers screens from `dataset/labels/*_baseline.json`.
2. Harvests unambiguous text targets that appear exactly once on each baseline screen.
3. Queries each configured VLM for every `(target, screen, profile)` triple.
4. Scores predictions with a ±30 px hit-test against the ground-truth bounding box.
5. Writes results to CSV.

Output:

```text
outputs/evaluation_results/evaluation_results_{model_id}.csv
```

For example, `VLM_MODEL=openai/gpt-4o-mini` writes `outputs/evaluation_results/evaluation_results_openai_gpt-4o-mini.csv`. The model name is normalized by replacing `/` with `_`; `USE_A11Y_TREE=true` adds `_with_tree` before `.csv`.

## Stage 3: Run McNemar analysis

Analyze all evaluation CSVs automatically:

```bash
uv run python -m mcnemar.cli
```

Analyze one file:

```bash
uv run python -m mcnemar.cli \
  --csv outputs/evaluation_results/evaluation_results_openai_gpt-4o-mini.csv
```

The analysis builds a paired contingency table for each model and profile, uses asymptotic McNemar's χ² when discordant pairs `n ≥ 25`, and uses exact binomial otherwise. It flags `Floor_Limited=Yes` when baseline accuracy is below 50%.

Output:

```text
outputs/mcnemar/mcnemar_results_{model_id}.csv
```

Compare vision-only and accessibility-tree result files:

```bash
uv run python -m mcnemar.cli \
  --compare-a outputs/evaluation_results/evaluation_results_openai_gpt-4o-mini.csv \
  --compare-b outputs/evaluation_results/evaluation_results_openai_gpt-4o-mini_with_tree.csv
```

This writes `outputs/mcnemar/mcnemar_compare_{model_id}.csv`.

## Standalone utilities

The collection tools can be run independently when an emulator is connected:

```bash
# Apply an accessibility profile manually
uv run python -m collection.device.layout_modifier elder_combo_max

# Reset emulator to baseline
uv run python -m collection.device.layout_modifier reset

# Capture a single screen (output goes to outputs/)
uv run python -m collection.capture.screenshot_pipeline my_capture

# Extract labels from a single XML file
uv run python -m collection.capture.bound_extractor outputs/my_capture.xml
```

The profile definitions and experimental design are in [`methods.md`](methods.md). Provider-specific setup is in [`integrations.md`](integrations.md).

