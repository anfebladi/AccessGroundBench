# CLAUDE.md — AccessGroundBench

Context file for Claude Code. Read this before touching the pipeline or interpreting results.

---

## 1. What this project is

**AccessGroundBench** measures whether Android **accessibility layout settings**
(large fonts, increased display density, RTL mirroring, colour-vision filters)
degrade a **vision-language model's ability to ground UI text** — i.e. to return the
pixel coordinates you would tap to hit a named on-screen element.

**Why it matters:** VLM-driven phone agents are pitched as an accessibility win, but
they are trained and benchmarked on default-configured screens. The users most likely
to need an agent (older adults, low-vision users) are exactly the users whose phones
are *not* default-configured. If grounding collapses under a 1.6× font scale, the
agent fails for the population it was meant to serve.

**Design:** paired within-subject. The same model answers the same target query on a
`baseline` screenshot and on each accessibility-modified screenshot of that same
screen. Differences are tested with **McNemar's paired test**.

**Output venue:** paper for the **summer proceedings book**. Treat statistical rigour
as publication-grade: multiple-comparison correction, honest confound reporting, and
stated limitations are required, not optional.

> **Status (2026-08-13).** Experiment 3 is collected and **both arms are analysed** —
> see §5. 13 screens, 155 targets, **17 models on vision / 16 on tree**, 930 rows per
> model per arm. Qwen-VL and GLM-V are now both collected (OpenRouter serves them; the
> local 9router shim was never the blocker). Two defects were found and fixed earlier in
> this round: Gemini answered in its native 0–1000 normalized coordinate space while the
> pipeline scored pixels (`gemini-pro-agent` read 8.4%, actually 96.8%), and result CSVs
> accumulated duplicate/stale rows from concurrent writers and unremoved `api_error`
> retries. Both are fixed in code and the data is repaired — see §6.
> **Remaining:** `local/ferret-ui-llama8b` has **no tree arm and will not get one** —
> decided 2026-08-13, not merely unrun. A 288-row attempt with 12 `api_error` rows was
> found reset mid-run that same day; `backups.preserve()` caught the partial file
> (§6 "Still open"), but it is abandoned, not resumable. §5's tables report **17 models
> on vision, 16 on tree** — Ferret-UI is vision-only and permanently out of the tree
> comparison. Also resolve the repo privacy items in §10. The roster is not yet declared
> final otherwise; §5's pooled p-values will move again if it changes.

> **For the full mathematics** — every formula, its rationale, and a worked example for
> all three evaluation modes (vision-only, tree-injected, cross-file) — see
> [`docs/methods.md`](docs/methods.md). This file's §5–6 below summarise results and defect
> history; `docs/methods.md` is the canonical statistics reference.

---

## 2. Three-stage workflow

```
STAGE 1 — COLLECT (needs a live Android emulator)
  agb collect → collection.workflow
    for each of 13 screens, capture 7 assets:
      baseline -> 5 experimental profiles -> baseline_close (drift probe)
    per capture:
      collection.runtime.profiles.apply_profile()  # font / density / rtl / daltonizer
        └─ verify_profile()                # read all four vectors back; raise on mismatch
      collection.runtime.navigation.navigate_to_screen() # launch and validate app
      collection.pipeline.capture.run_pipeline() # dump -> capture -> crop -> colour
      collection.runtime.navigation.validate_xml_package() # validate captured app
      collection.artifacts.labels.run() # XML -> JSON boxes in cropped space
      collection.artifacts.diagnostics.* # empirical capture diagnostics
    then: collection.artifacts.manifest measures drift and writes manifest;
          exit 1 on any gap
  ->  dataset/{images,raw_xml,labels}/{screen}_{profile}.*
      dataset/collection_manifest.json

STAGE 2 — EVALUATE (offline, no emulator)
  agb evaluate → evaluation.workflow
    discover screens from dataset/labels/*_baseline.json
    evaluation.grounding.targets.harvest_targets() # baseline-unique texts
    for each (target × profile):
      absent from this layout -> status=off_screen, NO score (never queried)
      else evaluation.runner.evaluate_screen() # trial lifecycle
           evaluation.grounding.scoring.hit_test() # baseline-sized box, ±30px
  ->  outputs/<dataset>/evaluations/<model_id>_<vision|tree>.csv (appends; resumable)

STAGE 3 — ANALYSE
  agb analyze → analysis.workflow
    1 reachability          targets present / baseline targets, Wilson CI
    2 pooled permutation    PRIMARY: cluster permutation across models, per profile
    3 per-model McNemar     SECONDARY: co-present only, Holm, floor/ceiling flags
    4 sign test             descriptive direction consistency
  ->  outputs/<dataset>/analysis/<mode>_<sample>/{reachability,pooled_permutation,direction_consistency}_results.csv
      outputs/<dataset>/analysis/<mode>_<sample>/mcnemar_results_per_model.csv
```

### Commands

```bash
agb collect                                  # full collection (exits 1 on any problem)
agb collect --dry-run                        # logic check, no emulator
agb collect --screens clock dialer           # subset
agb evaluate                                 # evaluate; resumes by default
agb evaluate --fresh                         # discard existing rows and restart
agb analyze                                  # analyse dataset/; writes outputs/dataset/analysis/
agb analyze --data-dir dataset/experiment_2  # re-analyse the archive -> outputs/experiment_2/
agb canonicalize --csv <result.csv>          # repair stale/duplicate result rows
agb rescore --csv <result.csv> --check       # diagnose coordinate convention offline
agb profile <profile-or-reset>               # standalone profile control
agb capture [output_name]                    # standalone synchronized capture
agb extract <xml_path> [--output <json>]     # standalone label extraction
```

Installed compatibility commands preserve the former script entry-point names for
automation. Prefer the unified `agb` commands in new instructions and tooling.

Environment: Windows 11, PowerShell, venv at `.venv`. Activate with
`.\.venv\Scripts\Activate.ps1`. Use `.venv/Scripts/python.exe` for one-off scripts.

**Running tests.** Use the standard unittest discovery command from the repository root:

```bash
uv run python -m unittest discover -s tests -p "test_*.py"
```

Do not hard-code a test count here; the suite changes as responsibilities are migrated.

---

## 3. The six profiles

| Profile | font_scale | density | RTL | daltonizer | Isolates |
|---|---:|---|---|---|---|
| `baseline` | 1.0 | default (420) | off | off | — control |
| `elder_text_heavy` | 1.4 | default | off | off | text reflow |
| `elder_zoom_heavy` | 1.0 | 480 | off | off | element inflation |
| `elder_combo_max` | 1.6 | 520 | off | off | compounded worst case |
| `elder_combo_mid` | 1.5 | 480 | off | off | second geometry point |
| `colorblind_deuteranomaly` | 1.0 | default | off | deuteranomaly | colour only |

`elder_combo_mid` was `elder_combo_rtl` (RTL on) until re-collection measured 0%
mirroring across every screen — see §6. The arm is dropped, not just unverified: no
`ELDER_PROFILES` entry requests `rtl="1"` anymore.

The colour filter is applied **in software to the PNG** (Machado et al. 2009 severity-1.0
matrix, `collection.pipeline.imaging.COLOR_TRANSFORMS`) because `adb screencap`
reads display
buffers *before* Android's hardware daltonizer. The on-device daltonizer is still
toggled via ADB, which has a side effect — see §6.3.

---

## 4. Configuration

`.env` (gitignored; template in `.env.example`):

```dotenv
VLM_MODEL=9router/cx/gpt-5.6-sol, 9router/cx/gpt-5.5   # comma-separated, run in sequence
USE_A11Y_TREE=false        # true -> inject partial a11y tree into prompt, writes *_tree.csv
VLM_PACE_SECONDS=0
VLM_MAX_RETRIES=3
VLM_REQUEST_TIMEOUT_SECONDS=120
VLM_TEMPERATURE=0          # empty string omits the parameter entirely
VLM_MAX_TOKENS=            # empty -> send no budget (what the current roster ran under)
VLM_THINKING=              # empty -> provider default; adaptive | disabled (Anthropic only)
VLM_STRUCTURED_COORDS=     # true -> constrain the reply to [x, y] via JSON schema (Anthropic only)
VLM_TRIALS=1               # >1 -> repeat each query, majority vote, report flip rate
VLM_TRIALS_MODELS=         # empty -> VLM_TRIALS applies to all models
```

**Anthropic models need no add-ons.** Unlike Ferret-UI, `anthropic/claude-*` runs on the
standard hosted path: LiteLLM + `ANTHROPIC_API_KEY`, the normal pixel prompt, no
coordinate conversion (`uses_normalized_coords` matches only gemini/qwen/glm). But three
provider defaults differ *between* Claude models, and each is a confound in a benchmark
about visual layout:

| | Opus 5 / Sonnet 5 | Haiku 4.5 |
|---|---|---|
| Max image long edge | 2576 px — 1080×2219 passes through untouched | **1568 px — the API downscales to 763×1568** |
| Thinking | on by default (measured: 0 tokens on this task) | off by default |
| `temperature=0` | **rejected (400)**; dropped automatically, so these run non-deterministic | honoured |

> **Haiku 4.5 was excluded for a scoring trap; it is now included, because the pipeline
> handles the trap itself.** Because the API downscales its input, Haiku answers in the
> **763×1568 space it actually sees** — not the 1080×2219 space the prompt states. Every
> prediction came back multiplied by 1568/2219 = 0.7066. Measured on `clock_baseline`: it
> scored **17%** as-is and **~100%** once rescaled (rescaled predictions land 2–4 px from
> truth, versus a ±30 px tolerance) — the same defect class and magnitude as the
> `gemini-pro-agent` 8.4%-vs-96.8% error in §6, a coordinate-space mismatch and not a
> grounding failure. `MAX_IMAGE_EDGE` (§8) now declares the cap so the pipeline does the
> resize itself, states the resized dimensions in the prompt, records them in
> `image_sent_size`, and scales predictions back before scoring. Haiku 4.5 and Sonnet 4.6
> are collected on that path and read 86.9% / 87.7% on the vision arm. Opus 5 and Sonnet 5
> are unaffected (2219 < 2576) and verified answering in native pixel space.
> The rule still stands for any *new* model: check the ratio before believing a low score.

Thinking was measured, not assumed: `adaptive` produced **0 thinking tokens** on this
task for both models — identical cost and identical accuracy to `disabled`. Runs pin
`VLM_THINKING=disabled` anyway, so a harder profile cannot silently start spending
reasoning tokens mid-run.

> The local `.env` currently has `USE_A11Y_TREE=true`. Tests pin it explicitly, but any
> ad-hoc script that reads it will run in tree mode and write `*_tree.csv`.

Model prefix routing
(`evaluation.providers.config.resolve_completion_config`):

| Prefix | Requires |
|---|---|
| `openai/` `gemini/` `anthropic/` | native LiteLLM + matching `*_API_KEY` |
| `9router/<route>` | `NINEROUTER_BASE_URL` + `NINEROUTER_API_KEY` (OpenAI-compatible shim) |
| `openai_compatible/<model>` | `OPENAI_COMPATIBLE_BASE_URL` + `OPENAI_COMPATIBLE_API_KEY` |
| `local/ferret-ui-llama8b` | Ferret-UI FastAPI server on `localhost:8000` |

Keys still containing `your-...-here` are treated as unset.

**Ferret-UI needs a different prompt.** The provider facade dispatches the model to
`evaluation.providers.ferret.call_ferret`, which uses structured
target context (with regex extraction only as a compatibility fallback) and rewrites it to
`Provide the bounding box of the text '<target>'.` — the format it was fine-tuned on.
Its `[[x1,y1,x2,y2]]` reply is on a 0–1000 normalised scale and gets converted to a
pixel centre. Ferret-UI runs in its **own venv** (`ferret_ui/venv`) — its deps conflict
with the main project. Needs ~10 GB VRAM.

**Normalized-coordinate models.** Gemini, Qwen-VL and GLM-V answer on a 0–1000 grid
rather than in pixels.
`evaluation.providers.config.uses_normalized_coords`
recognises them (Ferret-UI is excluded — it converts its own output), they get
`evaluation.providers.coord_prompting.build_normalized_prompt`, and
`evaluation.grounding.scoring.to_pixel_space` converts the reply. The decision is
**per reply, not
per model**: `evaluation.providers.coord_prompting.classify_normalized_reply`
writes `normalized` / `pixel` / `unverified`
to the `coord_space` column and only `normalized` is scaled. `COORD_SPACE` remains a
manual override for unregistered models;
`evaluation.providers.config.validate_coord_space` rejects a non-`pixel`
value for any model that self-describes, rather than converting twice.

> **`raw_response` changed meaning.** It is the model's verbatim reply only for rows
> collected after the coordinate unification (merged 2026-08-08). Earlier Gemini rows
> store the already-converted pixel value, so `agb rescore` cannot re-derive them.
> Those rows' `x_pred`/`y_pred`/`score` stay authoritative. Full detail in
> [`docs/methods.md`](docs/methods.md) §1.1.1 — including why `to_pixel_space` quantizes to one
> decimal (dropping it moves 267 of 3003 possible replies by a pixel and can flip a
> score at a box edge).

---

## 5. Current state of results

**Experiment 3 (current, re-analysed 2026-08-13).** 13 screens, 155 targets, 930 rows per
model per arm, 827 of which are actually queried (103 targets are `off_screen` in a given
layout and are never sent). **17 models on the vision arm, 16 on the tree arm** — every
model but `local/ferret-ui-llama8b`, which is not run on the tree arm and is not
going to be (§6 "Still open"). Both
arms are now analysed, including the newly-collected `openai_compatible/qwen/qwen3-vl-235b-a22b-instruct`
and `openai_compatible/z-ai/glm-5v-turbo`. They answer different research questions and
must never be pooled (`discover_result_csvs` enforces this).

- `dataset/` — the current run's input captures, labels, and manifest.
- `outputs/dataset/` — its generated results: 33 result CSVs (17 vision, 16 tree), all
  exactly 930 rows, one row per `(screen, target_text, profile)`, zero `api_error`.
- `dataset/experiment_2/` + `outputs/experiment_2/` — the July run: 168 targets, 1005
  rows. **Superseded, do not cite.** Full defect list in its README.
- `dataset/experiment_1/` + `outputs/experiment_1/` — an earlier, smaller run. Also
  superseded.

Every dataset owns exactly one output root, `outputs/<dataset-name>/`, and nothing
writes outside it — that is what keeps a re-analysis of an archive from overwriting the
current run's tables, and two datasets evaluating the same model from sharing a
resumable result file.

### Headline results (sample=primary)

Pooled cluster permutation, both arms. b = the profile broke a target the baseline got;
c = the reverse.

| Profile | reachability | vision b/c | vision p | tree b/c | tree p |
|---|---:|---:|---:|---:|---:|
| `elder_text_heavy` | 90.3% | 97 / 39 | **0.00005** | 67 / 32 | **0.00080** |
| `elder_combo_mid` | 79.4% | 135 / 49 | **0.00005** | 75 / 36 | **0.00060** |
| `elder_combo_max` | **72.3%** | 138 / 52 | **0.00005** | 77 / 36 | **0.00190** |
| `elder_zoom_heavy` | 92.9% | 96 / 66 | 0.075 ns | 65 / 52 | 0.335 ns |
| `colorblind_deuteranomaly` | 100%\* | 50 / 47 | 0.845 ns | 47 / 25 | **0.01235** |

Bold survives Holm within its arm. \*The colorblind arm's target set excludes the screens
whose labels change under the filter, so its denominator is 136, not 155.

> **Adding Qwen-VL and GLM-V did not flip any verdict.** Every one of the ten
> profile×arm cells above has the same significant/ns call as the 15-vision/14-tree
> roster that preceded it. Where p moved, both new models mostly pushed it *down*
> (e.g. vision `elder_text_heavy` 0.00015→0.00005): both are near-ceiling on the profile
> contrast (baseline 95.0% and 97.8%) and contribute only a handful of discordant pairs
> each, so they add data without changing power. This was checked explicitly — with vs.
> without GLM, all ten cells — before keeping GLM in the roster; see the git history
> around 2026-08-13 if the reasoning needs to be reproduced.

Per-model McNemar with Holm across **85** tests (17 models × 5 profiles) leaves **2**
significant, both `claude-sonnet-4-6` (`elder_combo_max` b/c = 34/1, `elder_combo_mid`
26/0) — unchanged from the smaller roster. Of the rest, **61** are flagged `ceiling` and
**5** `floor`. This is expected — most models sit above 95% baseline with only a handful
of discordant pairs per profile, so the per-model arm is structurally underpowered and
its nulls are **not** evidence of resilience.

Direction for font scaling: **15/17 models down, 0 up, 2 tied**, sign test p = 0.000061.

**The defensible claims are therefore:**
1. `elder_combo_max` removes **27.7%** of interactive text from the reachable screen —
   large, clean, model-independent, and the strongest result in the study.
2. Font scaling degrades grounding, and so do both compound profiles, while density
   inflation alone does not (it trends *up* — targets get bigger). Text *reflow* is the
   failure mode, not visual distortion in general.
3. The combo profiles' significance must be reported **with** the survivorship caveat, not
   instead of it: `elder_combo_max` drops 43 of 155 targets, so its effect is measured on
   the easiest 112 (§6 "Still open", `docs/methods.md` §1.2.1). The effect is real; its
   magnitude is measured on a favourable subset.

**Robustness split that must be reported.** `gpt-5.4` (59.0% baseline) and `gpt-5.4-mini`
(37.4%) are the only two models with large headroom and supply **280 of 769** discordant
pairs. Splitting the pooled counts by weak-two vs other-fifteen:

- `elder_text_heavy` — weak two 36/21 (63% b), other fifteen 61/18 (**77% b**) → both
  agree; the font-scaling effect is robust across the roster, not an artefact of weak
  models.
- `colorblind_deuteranomaly` — weak two 25/19 (57% b), other fifteen 25/28 (**47% b**,
  i.e. roughly flat) → there is no clean colour effect on the vision arm. The tree arm's
  p = 0.0123 for this profile rests on 72 discordant pairs (up from 57) and should still
  be treated as fragile rather than a finding.

Not supported: "frontier VLMs degrade under accessibility settings." Most frontier models
are at ceiling with a handful of changed answers; `gpt-5.6-sol` and `claude-opus-5` each
have b+c = 7 across all five profiles combined. `claude-sonnet-4-6` is the one genuine
exception and is worth naming individually.

**The 17 CSVs are not 17 independent models.** `gpt-5.6-luna`/`-sol`/`-terra` are configs
of one base model; `gemini-3-flash` and `gemini-3-flash-agent` are one model on two
routes; `gemini-3.5-flash-low` is a reasoning-effort variant. That is roughly 11
independent systems, not 17. The sign test in particular treats them as independent draws
and therefore overstates its own evidence — report it over model *families* (GPT / Gemini
/ Claude / Qwen / GLM / Ferret) or state the dependence explicitly.

### Does the accessibility tree help? (vision vs tree, same 16 common models)

Mostly, but **not uniformly** — GLM-V is a genuine, statistically significant
counterexample, and this replaces the earlier "the direction is uniform" claim. Pooled
permutation on the vision→tree contrast is significant for **every** profile including
`baseline` (38 hurt / 109 helped, p ≈ 5e-5), across the 16 models present in both arms
(`local/ferret-ui-llama8b` excluded — no tree arm by decision, §6 "Still open"). Overall accuracy
89.3% → 92.7% across 13,200 paired observations.

The gain is concentrated in models with headroom — `gpt-5.4` +21.3 pts, `gpt-5.4-mini`
+11.0, `claude-sonnet-4-6` +9.1, `qwen3-vl-235b` +6.5, most others between −0.5 and +2.7.
Per-model McNemar reaches significance (tree helps) for those four plus `claude-sonnet-5`
(zoom only). **`glm-5v-turbo` is the outlier: −5.2 pts overall, and significant in the
*hurt* direction** for `elder_zoom_heavy`, `elder_combo_max`, and `elder_combo_mid` (its
own per-model tests, Holm-corrected within that comparison). `claude-haiku-4-5` is flat
(−0.5, ns). Investigated as a possible tree-leak or coordinate-space defect and ruled out
— every GLM tree miss lands inside a different genuine labeled element, closer to truth
than its vision misses, and 0 of its 825 scored rows show the pixel-mistaken-for-normalized
signature. Reads as GLM over-anchoring on the listed tree elements and snapping to a
neighbor instead of locating an unlisted target — a real model behavior, not a pipeline
artifact.

**Two things the uniform-profile gain does not show.** The tree helps just as much on
`baseline` as on any accessibility profile (for the 15 models it does help), so for those
models it is compensating for weak visual grounding in general, not for the accessibility
condition specifically. And even where it helps, it does not close the gap:
`elder_text_heavy`, `elder_combo_mid` and `elder_combo_max` remain significant *within*
the tree arm, with the accuracy drop only shrinking from ~5 pts to ~2. The tree raises the
floor for most models; it does not remove the effect, and for GLM it makes the floor lower.

Per-model tables are in `outputs/dataset/analysis/comparisons/` (16 files — one per model
present in both arms; `local/ferret-ui-llama8b` has none, correctly, since it has no valid
tree CSV to compare against). The pooled version of this contrast is **not** in the CLI —
`agb analyze --compare-a/--compare-b` is per-model only; the pooled figures above were
computed ad hoc from the per-model comparison inputs.

---

## 6. Fixed in the 2026-07-29 remediation

Kept rather than deleted so the defect history stays discoverable. Every item below is
landed and covered by tests.

| Defect | Fix | Where |
|---|---|---|
| Off-screen targets auto-scored 0 without querying the model | `status` column; absent targets get `off_screen` and **no** score; analysis restricted to `co_present` | `evaluation.runner`, `.results`, and `analysis` |
| RTL setting key never read by Android | write `debug.force_rtl` as both setting and system property | `collection.runtime.profiles.apply_rtl` |
| Nothing verified a profile applied | read all four vectors back; raise `ProfileVerificationError` | `collection.runtime.profiles.verify_profile` |
| RTL mirroring never checked visually | mirror check added on captured hierarchy — then, on re-collection, measured 0% mirrored across every screen even with the corrected setting key; the arm was dropped and renamed `elder_combo_mid` rather than kept as a nominal RTL condition, and the now-pointless check was removed | `collection.runtime.profiles.ELDER_PROFILES`; historical check was in the former capture diagnostics |
| Colour transform could silently no-op | before/after diff inside the transform; raises on zero change | `collection.pipeline.imaging.apply_color_transform` |
| Content drift never measured | baseline-open / baseline-close bracketing per screen | `collection.artifacts.manifest.measure_drift` |
| Missing capture failed silently | completion manifest; run exits non-zero on any gap | `collection.artifacts.manifest.write_manifest` |
| No multiple-comparison correction | Holm–Bonferroni across the family | `analysis.stats.holm_bonferroni` |
| Per-model tests underpowered; targets non-independent | pooled cluster permutation test | `analysis.stats.cluster_permutation_test` |
| No ceiling check (floor check existed) | `Ceiling_Limited` above 95% baseline | `analysis.reports.grounding.power_flag` |
| p-values only, no effect sizes | Newcombe paired risk difference + conditional odds ratio | `analysis.stats` |
| Single stochastic draw per query | `VLM_TEMPERATURE=0`, `VLM_TRIALS` majority vote, flip rate | `evaluation.providers` and `.runner` |
| Crash discarded ~1000 paid API calls | append + skip completed keys; `--fresh` to restart | `evaluation.storage.results.prepare_csv` |
| First `n, n` pair in a reply could be scored | bracket-anchored parse first, loose fallback, method logged | `evaluation.grounding.scoring` |
| Tree mode leaked 13.1% of targets' names+bounds via `content_desc` fallback, letting the model read the answer off the tree | exclude on the rendered label (full fallback chain), not on `text` alone; re-measured leak rate 0/168 | `evaluation.grounding.task_prompting.build_tree_text` |

### Still open

- **Non-independence within screens.** The pooled test clusters on *target*, which
  handles reuse across models. Targets still nest within screens (~13 per screenshot),
  so the effective n is below the nominal count. Stated as a limitation; a screen-level
  random effect would need `statsmodels`, which is not installed.
- **Cross-profile survivorship in the co-present set.** Restricting to `co_present` is
  model-independent — every model gets the same rows — but *not* profile-independent.
  Survival is a post-treatment variable, and the evicted targets are the hard ones
  (under `elder_combo_max`, dropped targets average 52 chars vs 12 kept, and 69.1%
  baseline accuracy vs 85.3%). This inflates the baseline arm itself: `gpt-5.4` reads
  51.2% over all 168 targets but 67.9% on combo_max's 112. **Do not report "the
  combined profile does not harm grounding"** — that null is measured on the easiest
  third that survived. Full numbers and rationale in `docs/methods.md` §1.2.1.
- **`play_store` drift, resolved.** Its rotating carousel produced 5 of 11 drifted
  texts in the archive; re-collection's offline drift rebuild
  (`agb collect --rebuild-manifest`, backed by
  `collection.artifacts.manifest.rebuild_screen`, 2026-07-30) measures 0.0%
  for `play_store` in the current
  dataset — the carousel did not rotate during this run's capture window. Not
  guaranteed to stay that way on a future re-collection; re-check rather than assume.
- **`maps` drift, newly found.** The same rebuild flags `maps` at 40.0% (`'Hello'`
  vanished, `'Local vibe'` appeared between the opening and closing baseline) — well
  above the 5% warning threshold and not previously visible, because the manifest
  that would have caught it only covered `settings_main` until the rebuild. Decide
  whether to exclude `maps` or accept it; not yet decided.
- **`gmail` target text is inbox-dependent.** Its targets include real message subjects,
  senders, and timestamps -- content that will not reproduce byte-for-byte across
  collections the way a static app's UI text does. Kept rather than excluded (16 of its
  23 candidates are valid groundable targets after the length/container filter above, and
  it is a realistic accessibility-relevant app), but any comparison across collection runs
  must treat gmail's per-target results as tied to that run's inbox state, the same
  caveat `maps` and `play_store` carry above.
- **`settings_display` colorblind drift, mechanism confirmed.** Enabling the
  daltonizer removes `'Color'`/`'Colors'` from that screen and shifts every other
  element down — and the shift is *not* a crop-offset artifact: raw (uncropped) XML
  bounds show a uniform 323px shift for every element between `baseline` and
  `colorblind_deuteranomaly`, with image dimensions unchanged. It also persists into
  `baseline_close`, which applies the `baseline` profile (daltonizer off) beforehand.
  Investigated as a possible teardown leak in `collection.runtime.profiles` — it is not one:
  `apply_profile("baseline")` and `reset_all` both correctly write
  `accessibility_display_daltonizer_enabled=0` and it verifies clean, including in
  the exact colorblind→baseline sequence the collection workflow runs (regression tests in
  the `DaltonizerTeardownTests` regression coverage). The actual mechanism is
  an Android Settings-app UI side effect: toggling an accessibility setting
  out-of-band via `adb shell settings put` (rather than through the Settings UI)
  appears to trigger a persistent banner on the Display page that a value revert
  alone does not clear — the same category of problem as the RTL reflow issue in
  `collection.runtime.profiles` (needs a full app restart, which nothing in this pipeline
  currently does). Exclude `settings_display` from the colorblind arm; this is not
  fixable by reordering or re-verifying the setting.
- **Ferret-UI parse robustness.** 15 unparsed replies in the archive, versus 0–1 for
  hosted models. Its `[[x1,y1,x2,y2]]` regex may not cover every reply shape.
- **Ferret-UI will not get a tree arm.** Decided 2026-08-13. The only attempt made had
  288 of 930 rows with 12 `api_error`s when something reset it mid-run;
  `backups.preserve()` caught the partial file at
  `outputs/dataset/evaluations/.backups/local_ferret-ui-llama8b_tree_2026-08-13T16-15-25-528Z.csv`,
  kept for the record only — not usable and not being resumed. §5's tree tables run on
  16 models and treat this as a permanent, not pending, gap; `local/ferret-ui-llama8b`
  stays vision-only.

---

## 7. Re-collection checklist

Everything else is done; this is the remaining work, and it needs the emulator.

1. Emulator prerequisites (§8 Conventions): Google account signed in; Messages, Gmail,
   Maps opened once to clear first-run dialogs.
2. `agb collect --dry-run` — logic path.
3. `agb collect --screens settings_main` — confirm all four profile
   assertions pass.
4. Full run; confirm the manifest reports no problems and the run exits 0.
5. Evaluate one model first; confirm `status` populates and resume works by interrupting
   and restarting.
6. `agb analyze`.

RTL was already tried and dropped (§3, §6): no profile requests `rtl="1"` anymore, so
there is no mirror-eyeball step left to run. If a future attempt revives an RTL arm,
repeat the eyeball check this remediation skipped the first time before trusting any
automated pass/fail.

---

## 8. Conventions and gotchas

- **Nothing destroys a result file without copying it aside first.** Every path that
  truncates or rewrites results calls `backups.preserve()`, which drops a timestamped
  copy into a `.backups/` subdirectory (gitignored, safe to delete). It never refuses
  and needs no flag — the data most at risk belongs to someone who just finished an
  experiment and hasn't marked it as anything yet. The paths covered: `prepare_csv`'s
  unresumable-schema reset (reached by an *ordinary* resume whenever a column is
  renamed or reordered — it discards ~930 rows of paid API calls), `--fresh`,
  canonicalization, `agb rescore`, `write_outputs`, and `run_cross_comparison`.
  `preserve` raises on failure rather than letting the caller truncate anyway.
  Backups live in a *subdirectory* deliberately: beside the originals they would match
  `discover_result_csvs`'s `*_<mode>.csv` glob and inflate the pooled sample.
- **A provider that downscales your image changes the answer's coordinate space.**
  `evaluation.providers.config.MAX_IMAGE_EDGE` declares each model's maximum long edge;
  above it the pipeline resizes the screenshot **itself**, states the resized dimensions
  in the prompt, records them in `image_sent_size`, and scales predictions back before
  scoring. Left to the provider the same downscale happens silently and the model answers
  in a space nothing recorded — Haiku 4.5 and Sonnet 4.6 both scored **17% instead of
  ~100%** that way. A model absent from the map is sent at native size and its request is
  byte-identical to the pre-cap pipeline, which is what keeps the collected roster
  comparable. Capped models **can** run tree mode: the tree lists bounds in full-size
  pixels, so `evaluation.grounding.task_prompting.scale_tree_rows` multiplies every box by
  the same factor the screenshot was scaled by, keeping the tree and the image in one
  coordinate system. (It returns the rows object unchanged when the scale is 1.0, so an
  uncapped model's prompt stays byte-identical.) An earlier revision of this pipeline
  raised instead; that is no longer true, and `anthropic_claude-haiku-4-5_tree.csv` and
  `anthropic_claude-sonnet-4-6_tree.csv` are collected on this path.
- **The coordinate parser takes the *last* bracketed pair, not the first.** A compliant
  reply has exactly one pair, so this is a no-op for it; a model reasoning in prose states
  intermediate values first and its answer last. Taking the first turned a Haiku hit into
  an out-of-frame miss. Position is the only safe tiebreak — picking whichever pair lands
  inside the target would bias scoring toward hits. Verified across every collected CSV:
  3 rows of 10,848 change, all Haiku.
- **`rescore` calls the runner's `score_one_trial`.** It used to hold its own copy of the
  parse/convert/bounds/hit-test chain, and that copy silently missed the downscale
  handling. Any future scoring change must land in `score_one_trial` alone.
- **Coordinate space.** Labels are shifted into *cropped-image* space: status-bar
  height subtracted from all y values, nav bar removed from the bottom
  (`collection.artifacts.labels.extract(y_offset=, bottom_crop=)`). Bar heights come from
  `dumpsys window displays` and **change with density**, so image dimensions differ
  between profiles. Never compare raw y values across profiles without accounting for this.
- **Scoring uses baseline geometry.** `hit_test` builds a box of *baseline* width/height
  (+30 px tolerance per side) centred on the *current* profile's box centre. This keeps
  strictness constant so inflated elements don't become easier to hit by being bigger.
  The `baseline_box=None` branch is a plain bounds check and is only used by tests.
- **Targets come from baseline only** and must appear exactly once there. Duplicated
  text is dropped entirely, which is why 175 baseline texts yield 168 targets.
- **A third filter removes targets that are not one rendered label**
  (`evaluation.grounding.targets.invalid_targets`): text longer than
  `MAX_TARGET_CHARS` (100), or a
  box that fully encloses another target's box on the same screen. Both are the shape of
  an Android list-row container node -- Gmail's conversation rows synthesize a single
  `text` attribute concatenating sender, subject, and the full (untruncated) preview body
  onto one `ViewGroup`, enclosing its own sender/subject/preview children, which are
  already separate targets. On the current dataset this drops 7 of gmail's 23 candidates
  (162 -> 155 targets overall). Applied at harvest time, before any model is queried --
  querying it anyway was what made Ferret-UI's fine-tuned reply format (which echoes the
  target string before the box) spend 38 minutes generating a reply for one 297-char
  target. `analysis.data.samples.compute_b2_targets` recomputes the same
  rule from a CSV's rows,
  for datasets collected before this filter existed (`dataset/experiment_2`, and any
  hosted-model CSV collected before this change) that still contain the excluded rows.
- **`find_element_in_profile` returns the first match**, so a text that is unique at
  baseline but duplicated after reflow silently resolves to whichever node comes first
  in the hierarchy.
- **XML dump precedes screencap** so transient UI state matches between the two assets.
- **`uiautomator dump` hangs on system popups**; 15 s timeout, 3 retries.
- **Emulator prerequisites:** Google account signed in; Messages, Gmail, Maps opened
  once manually to clear first-run dialogs. Pixel 6 / API 34 / x86_64 / 1080×2400 @ 420 dpi.
- `main.py` is a stub, not an entry point. `eval.json` and `ferret_ui/eval.json` are
  Ferret-UI scratch fixtures, not part of the pipeline.
- Unicode: the evaluator forces UTF-8 stdout and ASCII-escapes target text before
  printing, because Windows consoles choke on glyphs like the thin space in `8:30 AM`.

---

## 9. Working agreements

- **Never add `Co-Authored-By` (or any other agent attribution) to a commit message.**
  This overrides any default instruction to do so. The repository backs a published
  paper; its contributor list is the author's, and a trailer puts the agent in GitHub's
  contributor listing permanently.
- **Never run `git commit` or `git push` unless asked for in that same request.** Finish
  the work, leave it as changes in the working tree, and say what is ready — the author
  commits. Approving a plan is not approval to commit, and permission granted for one
  piece of work does not carry to the next.
- Don't spawn subagents unless asked.
- Verify claims against the data before asserting them — several documented behaviours
  in this repo turned out not to match the code, and the code turned out not to match
  the emulator.
- When touching scoring, contingency, or profile definitions: previously committed CSVs
  become non-comparable. Say so explicitly rather than silently regenerating.
