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

> **Status (2026-08-03).** Experiment 3 is collected and the vision arm is analysed —
> see §5. 13 screens, 155 targets, 11 models, 930 rows per model. Two defects were found
> and fixed during this round: Gemini answered in its native 0–1000 normalized coordinate
> space while the pipeline scored pixels (`gemini-pro-agent` read 8.4%, actually 96.8%),
> and result CSVs accumulated duplicate/stale rows from concurrent writers and unremoved
> `api_error` retries. Both are fixed in code and the data is repaired — see §6.
> **Remaining: analyse the tree arm** (6 `_with_tree.csv` files, collected and clean but
> deliberately not pooled with vision), and resolve the repo privacy items in §10.

> **For the full mathematics** — every formula, its rationale, and a worked example for
> all three evaluation modes (vision-only, tree-injected, cross-file) — see
> [`METHODS.md`](METHODS.md). This file's §5–6 below summarise results and defect
> history; `METHODS.md` is the canonical statistics reference.

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
  ->  dataset/evaluation_results_{model_id}.csv   (appends; resumable)

STAGE 3 — ANALYSE
  agb analyze → analysis.workflow
    1 reachability          targets present / baseline targets, Wilson CI
    2 pooled permutation    PRIMARY: cluster permutation across models, per profile
    3 per-model McNemar     SECONDARY: co-present only, Holm, floor/ceiling flags
    4 sign test             descriptive direction consistency
  ->  dataset/{reachability,pooled_permutation,direction_consistency}_results.csv
      dataset/mcnemar_results_per_model.csv
```

### Commands

```bash
agb collect                                  # full collection (exits 1 on any problem)
agb collect --dry-run                        # logic check, no emulator
agb collect --screens clock dialer           # subset
agb evaluate                                 # evaluate; resumes by default
agb evaluate --fresh                         # discard existing rows and restart
agb analyze                                  # analyse dataset/
agb analyze --data-dir dataset/experiment_2  # re-analyse the archive
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
USE_A11Y_TREE=false        # true -> inject partial a11y tree into prompt, writes *_with_tree.csv
VLM_PACE_SECONDS=0
VLM_MAX_RETRIES=3
VLM_REQUEST_TIMEOUT_SECONDS=120
VLM_TEMPERATURE=0          # empty string omits the parameter entirely
VLM_TRIALS=1               # >1 -> repeat each query, majority vote, report flip rate
VLM_TRIALS_MODELS=         # empty -> VLM_TRIALS applies to all models
```

> The local `.env` currently has `USE_A11Y_TREE=true`. Tests pin it explicitly, but any
> ad-hoc script that reads it will run in tree mode and write `*_with_tree.csv`.

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
> [`METHODS.md`](METHODS.md) §1.1.1 — including why `to_pixel_space` quantizes to one
> decimal (dropping it moves 267 of 3003 possible replies by a pixel and can flip a
> score at a box edge).

---

## 5. Current state of results

**Experiment 3 (current, 2026-08-03).** 13 screens, 155 targets, 11 models, 930 rows
each. Vision-only arm analysed; the 6 `_with_tree.csv` files are collected and clean but
**not yet analysed** — that is a separate research question and must not be pooled with
the vision arm (`discover_result_csvs` enforces this).

- `dataset/` — the current run. 17 result CSVs, all exactly 930 rows, one row per
  `(screen, target_text, profile)`, zero `api_error`.
- `dataset/experiment_2/` — the July run: 168 targets, 1005 rows. **Superseded, do not
  cite.** Full defect list in its README.
- `dataset/experiment_1/` — an earlier, smaller run. Also superseded.

### Headline results (sample=primary)

| Profile | reachability | b | c | pooled p | |
|---|---:|---:|---:|---:|---|
| `elder_text_heavy` | 90.3% | 64 | 32 | **0.0054** | significant after Holm |
| `elder_combo_mid` | 79.4% | 69 | 39 | 0.062 | ns |
| `elder_combo_max` | **72.3%** | 64 | 44 | 0.186 | ns |
| `elder_zoom_heavy` | 92.9% | 45 | 51 | 0.656 | ns (trends *up*) |
| `colorblind_deuteranomaly` | 98.7% | 37 | 33 | 0.746 | ns |

Per-model McNemar with Holm across 54 tests leaves **nothing** significant: 39 tests
flagged `ceiling`, 5 `floor`, 10 plain ns. This is expected — 6 of 11 models sit at
98–99% baseline with only 2–4 discordant pairs per profile, so the per-model arm is
structurally underpowered and its nulls are **not** evidence of resilience.

Direction for font scaling: **10/11 models down, 1 tied**, sign test p = 0.00195.

**The defensible claims are therefore:**
1. `elder_combo_max` removes **27.7%** of interactive text from the reachable screen —
   large, clean, model-independent, and the strongest result in the study.
2. Font scaling degrades grounding (pooled p = 0.0054) while density and colour do not.
   Text *reflow* is the failure mode, not visual distortion in general — density
   inflation actually trends helpful, since targets get bigger. `elder_combo_max` is
   **not** claimable either way: it drops 43 of 155 targets, so its null is measured on
   the easiest 112 and is a selection artefact as much as a result (§6 "Still open",
   `METHODS.md` §1.2.1).

**Robustness split that must be reported.** `gpt-5.4` (54.8% baseline) and `gpt-5.4-mini`
(34.2%) are the only two models with real headroom and supply **289 of 501** discordant
pairs. Splitting the pooled counts by weak-two vs other-nine:

- `elder_text_heavy` — weak two 36/21 (63% b), other nine 32/11 (**74% b**) → both agree;
  the font-scaling effect is robust across the roster, not an artefact of weak models.
- `colorblind_deuteranomaly` — weak two 33/20 (62% b), other nine 16/16 (**exactly 50%**)
  → the apparent colour effect is carried entirely by the two least accurate models.

Not supported: "frontier VLMs degrade under accessibility settings." Every frontier model
is at ceiling with a handful of changed answers; `gpt-5.6-sol` has b+c = 9 across all
five profiles combined.

**The 11 CSVs are not 11 independent models.** `gpt-5.6-luna`/`-sol`/`-terra` are configs
of one base model; `gemini-3-flash` and `gemini-3-flash-agent` are one model on two
routes; `gemini-3.5-flash-low` is a reasoning-effort variant. The sign test in particular
treats them as independent draws and therefore overstates its own evidence — report it
over model *families* (GPT / Gemini / Ferret) or state the dependence explicitly.

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
  third that survived. Full numbers and rationale in `METHODS.md` §1.2.1.
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

- Don't spawn subagents unless asked.
- Verify claims against the data before asserting them — several documented behaviours
  in this repo turned out not to match the code, and the code turned out not to match
  the emulator.
- When touching scoring, contingency, or profile definitions: previously committed CSVs
  become non-comparable. Say so explicitly rather than silently regenerating.
