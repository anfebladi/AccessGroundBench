# Experiment 2 — ARCHIVED, SUPERSEDED, DO NOT CITE

> **Warning.** The results in this directory contain three methodological defects that
> invalidate the headline finding. They are retained for provenance and for regression
> testing the corrected analysis code. **Do not cite these numbers.**

## Contents

| Path | Description |
|---|---|
| `images/`, `raw_xml/`, `labels/` | 77 captures (13 screens × 6 profiles, minus one — see Defect 4) |
| `outputs/archives/experiment_2/evaluation_results_*.csv` | 7 models × 1005 rows, vision-only (`USE_A11Y_TREE=false`) |
| `outputs/archives/experiment_2/mcnemar_results_*.csv` | Per-model McNemar output, uncorrected |

**Collected:** 2026-07-24 (commit `86a7435`, "new dataset")
**Evaluated:** 2026-07-25 to 2026-07-26 (commits `c75993f`, `4092619`)
**Archived:** 2026-07-29

Emulator: Pixel 6, Android 14 (API 34), x86_64, 1080×2400 @ 420 dpi.

## What these results claim

24 of 35 model × profile tests reported statistically significant degradation in VLM
grounding under accessibility layout changes, including all 5 profiles for `gpt-5.5`.

## Why they are wrong

### Defect 1 — off-screen targets auto-scored 0 without querying the model

`vlm_eval/runner.py` (at time of collection) wrote `[OFF-SCREEN]` with `score=0`
whenever a target text was absent from the modified layout's XML, **without ever calling
the model**. `mcnemar_analysis.py` then counted those rows as model failures,
indistinguishable from genuine mislocalisation.

Targets are harvested *from* the baseline labels, so a target is present in baseline by
definition — confirmed: **140 off-screen rows per model, 0 in the baseline arm.** The
penalty is one-sided by construction and can only push the comparison one direction.

It also systematically penalises *better* models: a target can only be scored "broken" if
the model got it right at baseline, so a 98%-accurate model exposes ~168 targets to the
penalty while a 34%-accurate model exposes ~57. This is why these results perversely
rank frontier models as the most fragile.

| Model | degradation `b` | of which off-screen | share |
|---|---:|---:|---:|
| gpt-5.6-sol | 133 | 126 | 94.7% |
| gpt-5.6-terra | 135 | 123 | 91.1% |
| gpt-5.5 | 148 | 134 | 90.5% |
| ferret-ui-llama8b | 144 | 116 | 80.6% |
| gpt-5.6-luna | 151 | 116 | 76.8% |
| gpt-5.4 | 95 | 31 | 32.6% |
| gpt-5.4-mini | 75 | 18 | 24.0% |

Restricting to targets present in both layouts: **24/35 significant → 4/35 → 1/35 under
Holm–Bonferroni.** `gpt-5.5` and `gpt-5.6-sol` drop to zero significant profiles.

Illustrative: `gpt-5.6-sol` / `elder_combo_max` reads 97.0% → 66.1% (p = 1.5e-12) in
`outputs/archives/experiment_2/mcnemar_results_9router_cx_gpt-5.6-sol.csv`. On co-present targets it is
99.1% → 99.1%, `b = 0, c = 0` — not one changed answer.

### Defect 2 — RTL was never applied

`layout_modifier.py` wrote `settings put global development_settings_force_rtl`, a key
Android does not read. Verified against these captures: comparing off-centre shared text
between `elder_zoom_heavy` (RTL off) and `elder_combo_rtl` (RTL "on") across all 13
screens gives **0 mirrored, 68 unchanged**. Not one element moved.

`elder_combo_rtl` in this dataset is therefore **font 1.5 + density 480**, a second
geometry profile — not a mirroring profile. Any RTL claim based on it is unsupported.

### Defect 3 — content drift between captures

`colorblind_deuteranomaly` is geometrically identical to `baseline`, so its labels should
match exactly. **6.3% of texts differ** (11 of 175):

- `play_store` — 5 texts vanish, 2 appear (rotating promo carousel)
- `settings_display` — `Colors` → `Color contrast`, `Default` appears. Self-inflicted:
  enabling the on-device daltonizer changes the content of the very page being measured.
- `maps` — `Ask Maps` appears

Captures were not bracketed by repeated baselines, so drift was never measured. Any
effect smaller than ~6% here is indistinguishable from capture noise.

### Defect 4 — one capture missing

`photos_elder_text_heavy` was never captured (77 of 78 files). `orchestrator.run_screen`
caught the failure, printed `[ERROR]`, and continued, so the gap was silent. It shrinks
`elder_text_heavy` to 165 pairs while every other profile has 168 — an asymmetry
invisible in the analysis output.

### Additional limitations

- No multiple-comparison correction across 35 tests.
- Targets nest within screens; McNemar assumes independent pairs.
- Single trial per query with `temperature` unset, so every score is one stochastic draw.
- No ceiling-effect check, despite `gpt-5.5` and `gpt-5.6-sol` sitting at 98–99% baseline
  where a null result is uninformative rather than evidence of resilience.

## What survives re-analysis

Re-analysing these same CSVs correctly (off-screen excluded, RTL arm dropped, pooled
across models with per-target cluster permutation) yields:

| Profile | b | c | pooled p | |
|---|---:|---:|---:|---|
| `elder_text_heavy` | 61 | 13 | **0.00005** | significant after correction |
| `elder_zoom_heavy` | 37 | 54 | 0.174 | ns (trends up) |
| `elder_combo_max` | 44 | 33 | 0.311 | ns |
| `colorblind_deuteranomaly` | 22 | 29 | 0.392 | ns |

Direction is unanimous for font scaling: 7/7 models down.

Plus a clean model-independent result: **`elder_combo_max` removes 56 of 168 targets
(33%) from the reachable screen.**

## Regression use

These archived CSVs are the fixture for verification step 7 of the remediation plan: the
rewritten `mcnemar_analysis.py` must reproduce the numbers in the table above when run
against `outputs/archives/experiment_2/` with source captures and labels from this
directory. If it does not, the rewrite is wrong.
