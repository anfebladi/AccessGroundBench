# Evaluation runbook

This runbook evaluates captures already under `dataset/`. It does not collect
data or change an Android device. Do not run `agb collect`, `agb profile`, `agb
capture`, or any command that uses ADB.

## Before starting

Configure `VLM_MODEL` and provider credentials in `.env` as described in the
[setup guide](../setup.md). Do not put real keys or accounts in this repository.
Do not change `VLM_MODEL` while a run is in progress. A model ID determines the
result filename:

```text
dataset/evaluation_results_{model ID with / replaced by _}.csv
```

When `USE_A11Y_TREE` enables the tree prompt, `_with_tree` is inserted before
`.csv` (for example, `evaluation_results_openrouter_qwen_qwen3-vl-235b-a22b-instruct_with_tree.csv`).

`USE_A11Y_TREE` accepts `true`, `1`, or `yes` for tree mode; `false`, `0`,
`no`, or an unset variable for vision-only mode. Any other value makes the
command fail; fix it before retrying.

The current profiles are exactly `elder_text_heavy`, `elder_zoom_heavy`,
`elder_combo_max`, `elder_combo_mid`, and `colorblind_deuteranomaly`.
`elder_combo_rtl` is not a current profile. The [collection guide](../collection.md)
documents how existing captures were produced; it is not needed to run this
evaluation.

### Coordinate convention

Predictions are scored in cropped-image pixels or a 0–1000 normalized grid.
`COORD_SPACE` may be `pixel` or `norm1000`, but is a manual override: models
whose provider already detects and converts their coordinate scale must not be
overridden (that would convert twice). For an existing result, compare both
conventions without API calls first:

```bash
agb rescore --csv dataset/evaluation_results_MODEL.csv --check
```

If the check identifies the other convention, repair stored scores (the command
writes a `.csv.bak` backup) and rerun analysis:

```bash
agb rescore --csv dataset/evaluation_results_MODEL.csv --coord-space norm1000
```

Use the matching `pixel` command when that is selected. Re-check after changing
`USE_A11Y_TREE`: the tree includes pixel bounds and can change how a model
answers. If both conventions score materially, report mixed coordinate formats
instead of choosing one.

Optional request controls are `VLM_PACE_SECONDS`, `VLM_MAX_RETRIES`, and
`VLM_REQUEST_TIMEOUT_SECONDS`. `VLM_TRIALS` repeats queries for stability;
`VLM_TRIALS_MODELS` can limit repeats to a comma-separated model subset.
Repeats measure stochastic stability and add no statistical power.

## Stages

### 1. Vision-only evaluation

Leave `USE_A11Y_TREE` unset or set it to `false`, then run against existing
captures:

```bash
agb evaluate
agb analyze --csv dataset/evaluation_results_MODEL.csv
```

Always pass `--csv` to `analyze`; the bare command discovers every result file
in `dataset/`.

### 2. Tree evaluation (only when the question requires it)

Set `USE_A11Y_TREE=true` without changing `VLM_MODEL`, then run:

```bash
agb evaluate
agb analyze --csv dataset/evaluation_results_MODEL_with_tree.csv --mode tree
```

Tree results are a separate CSV and do not overwrite vision-only results. Run
this arm only when the research question calls for the accessibility tree.

### 3. Compare the two prompt paths (optional)

When both files exist, supply both paths together:

```bash
agb analyze \
  --compare-a dataset/evaluation_results_MODEL.csv \
  --compare-b dataset/evaluation_results_MODEL_with_tree.csv
```

Comparison mode requires both `--compare-a` and `--compare-b` and ignores
`--csv`. It compares two result files; it is not a test of a profile-protection
interaction and must not be reported as one.

## Resume and recovery

`agb evaluate` resumes completed rows by default and uses a per-result lock.
Use `--fresh` to discard existing rows and start over. Use `--force-unlock`
only to remove a stale lock left by a killed process; it does not clear rows.
Do not change `VLM_MODEL` mid-run or use a different model to work around an
error. See [troubleshooting](../troubleshooting.md) for provider, timeout, and
analysis failures.

## Reporting results

Report the full path of every CSV written, the model ID, prompt mode, coordinate
space, trial settings, and any retries or failures. Interpret analysis with the
[methods hub](../methods.md): the pooled cluster permutation test is
primary, while per-model McNemar results are secondary. A `floor` flag (baseline
accuracy below 50%) or `ceiling` flag (above 95%) is underpowered, not evidence
of resilience or failure. Include reachability and grounding separately, and
state whether any comparison is a file-to-file prompt comparison rather than
a profile-protection interaction.

For command details, see the [CLI reference](../cli-reference.md). For
estimands and limitations, continue to the [methods hub](../methods.md).
