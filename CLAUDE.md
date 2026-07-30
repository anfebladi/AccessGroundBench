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

> **Status (2026-07-29).** Experiment 2 was audited, found to have three invalidating
> defects, and archived to `dataset/experiment_2/`. All code fixes are landed and the
> analysis is rebuilt. **The remaining step is re-collection on the emulator** — see §7.
> A separate leak found the same day in the accessibility-tree exclusion logic is also
> fixed — see `METHODS.md` §3 — and `USE_A11Y_TREE` was reset to `false` pending review.

> **For the full mathematics** — every formula, its rationale, and a worked example for
> all three evaluation modes (vision-only, tree-injected, cross-file) — see
> [`METHODS.md`](METHODS.md). This file's §5–6 below summarise results and defect
> history; `METHODS.md` is the canonical statistics reference.

---

## 2. Three-stage workflow

```
STAGE 1 — COLLECT (needs a live Android emulator)
  orchestrator.py
    for each of 13 screens, capture 7 assets:
      baseline -> 5 experimental profiles -> baseline_close (drift probe)
    per capture:
      layout_modifier.apply_profile()      # ADB settings: font / density / rtl / daltonizer
        └─ verify_profile()                # read all four vectors back; raise on mismatch
      app_navigator.navigate_to_screen()   # am start, confirm foreground pkg, dismiss perms
      screenshot_pipeline.run_pipeline()   # uiautomator dump -> screencap -> pull -> crop -> colour xform
      app_navigator.validate_xml_package() # confirm XML belongs to the intended app
      bound_extractor.run()                # XML -> JSON boxes, y-shifted into cropped space
      capture_checks.rtl_applied()         # RTL profiles only: did the layout mirror?
    then: measure_drift() over the two baselines; write manifest; exit 1 on any gap
  ->  dataset/{images,raw_xml,labels}/{screen}_{profile}.*
      dataset/collection_manifest.json

STAGE 2 — EVALUATE (offline, no emulator)
  vlm_evaluator.py
    discover screens from dataset/labels/*_baseline.json
    vlm_eval/targets.harvest_targets()     # texts appearing EXACTLY ONCE in baseline
    for each (target × profile):
      absent from this layout -> status=off_screen, NO score (never queried)
      else vlm_eval/runner.evaluate_screen()  # prompt, call model x VLM_TRIALS, majority vote
           vlm_eval/scoring.hit_test()        # baseline-sized box at current centre, ±30px
  ->  dataset/evaluation_results_{model_id}.csv   (appends; resumable)

STAGE 3 — ANALYSE
  mcnemar_analysis.py
    1 reachability          targets present / baseline targets, Wilson CI
    2 pooled permutation    PRIMARY: cluster permutation across models, per profile
    3 per-model McNemar     SECONDARY: co-present only, Holm, floor/ceiling flags
    4 sign test             descriptive direction consistency
  ->  dataset/{reachability,pooled_permutation,direction_consistency}_results.csv
      dataset/mcnemar_results_per_model.csv
```

### Commands

```bash
python orchestrator.py                        # full collection (exits 1 on any problem)
python orchestrator.py --dry-run              # logic check, no emulator
python orchestrator.py --screens clock dialer # subset
python vlm_evaluator.py                       # evaluate; resumes by default
python vlm_evaluator.py --fresh               # discard existing rows and restart
python mcnemar_analysis.py                    # analyse dataset/
python mcnemar_analysis.py --data-dir dataset/experiment_2   # re-analyse the archive
python mcnemar_analysis.py --include-rtl      # only after RTL passes the mirror check
```

Environment: Windows 11, PowerShell, venv at `.venv`. Activate with
`.\.venv\Scripts\Activate.ps1`. Use `.venv/Scripts/python.exe` for one-off scripts.

**Running tests.** `pytest` is *not* installed and `tests/` has no `__init__.py`, so
`unittest discover` fails on it. Use:

```bash
.venv/Scripts/python.exe -c "import sys,unittest,pathlib; sys.path[:0]=['.','tests']; \
unittest.main(argv=['x','discover'],module=None,exit=False) if 0 else \
unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromNames( \
[p.stem for p in sorted(pathlib.Path('tests').glob('test_*.py'))]))"
```

155 tests, all passing as of 2026-07-29.

---

## 3. The six profiles

| Profile | font_scale | density | RTL | daltonizer | Isolates |
|---|---:|---|---|---|---|
| `baseline` | 1.0 | default (420) | off | off | — control |
| `elder_text_heavy` | 1.4 | default | off | off | text reflow |
| `elder_zoom_heavy` | 1.0 | 480 | off | off | element inflation |
| `elder_combo_max` | 1.6 | 520 | off | off | compounded worst case |
| `elder_combo_rtl` | 1.5 | 480 | **on (BROKEN — see §6.2)** | off | mirroring |
| `colorblind_deuteranomaly` | 1.0 | default | off | deuteranomaly | colour only |

The colour filter is applied **in software to the PNG** (Machado et al. 2009 severity-1.0
matrix, `screenshot_pipeline.COLOR_TRANSFORMS`) because `adb screencap` reads display
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

Model prefix routing (`vlm_provider.resolve_completion_config`):

| Prefix | Requires |
|---|---|
| `openai/` `gemini/` `anthropic/` | native LiteLLM + matching `*_API_KEY` |
| `9router/<route>` | `NINEROUTER_BASE_URL` + `NINEROUTER_API_KEY` (OpenAI-compatible shim) |
| `openai_compatible/<model>` | `OPENAI_COMPATIBLE_BASE_URL` + `OPENAI_COMPATIBLE_API_KEY` |
| `local/ferret-ui-llama8b` | Ferret-UI FastAPI server on `localhost:8000` |

Keys still containing `your-...-here` are treated as unset.

**Ferret-UI needs a different prompt.** `vlm_provider.call_vlm` detects the model,
regex-extracts the target from the standard prompt, and rewrites it to
`Provide the bounding box of the text '<target>'.` — the format it was fine-tuned on.
Its `[[x1,y1,x2,y2]]` reply is on a 0–1000 normalised scale and gets converted to a
pixel centre. Ferret-UI runs in its **own venv** (`ferret_ui/venv`) — its deps conflict
with the main project. Needs ~10 GB VRAM.

---

## 5. Current state of results

**No current results.** Experiment 2 was archived on 2026-07-29 after an audit found
three invalidating defects; the code is fixed but re-collection has not run yet.

- `dataset/experiment_2/` — the July run: 13 screens, 168 targets, 7 models,
  1005 rows each. **Superseded, do not cite.** Full defect list in its README.
- `dataset/experiment_1/` — an earlier, smaller run. Also superseded.
- `dataset/` — empty of captures until the orchestrator is re-run.

### What the archived data still shows once re-analysed correctly

Running the current `mcnemar_analysis.py` against `dataset/experiment_2` reproduces
these, and doing so is the regression test for the analysis code (§9):

| Profile | reachability | b | c | pooled p | |
|---|---:|---:|---:|---:|---|
| `elder_text_heavy` | 88.5% | 61 | 13 | **0.00005** | significant after Holm |
| `elder_zoom_heavy` | 89.9% | 37 | 54 | 0.172 | ns (trends *up*) |
| `elder_combo_max` | **66.7%** | 44 | 33 | 0.313 | ns |
| `colorblind_deuteranomaly` | 96.4% | 22 | 29 | 0.395 | ns |

Per-model McNemar with Holm across 28 tests leaves **only** `gpt-5.4-mini` /
`elder_text_heavy` (p=0.00098) significant. Every frontier model is flagged `ceiling`
(98–99% baseline on co-present targets), meaning underpowered, **not** resilient.

Direction is unanimous for font scaling: **7/7 models down**, sign test p = 0.016.

**The defensible claims are therefore:**
1. `elder_combo_max` removes a third of interactive text from the reachable screen —
   large, clean, model-independent.
2. Font scaling degrades grounding (pooled p = 0.00005) while density and colour do
   not. Text *reflow* is the failure mode, not visual distortion in general — density
   inflation actually trends helpful, since targets get bigger. `elder_combo_max` is
   **not** claimable either way: it drops 56 of 168 targets, so its null is measured on
   the easiest 112 and is a selection artefact as much as a result (§6 "Still open",
   `METHODS.md` §1.2.1).

Not supported: "frontier VLMs degrade under accessibility settings." On visible
elements `gpt-5.5` goes 99.1% → 98.2% under `elder_combo_max`, and `gpt-5.6-sol` has
`b=0, c=0` — not one changed answer. (That 99.1% is the *restricted* baseline over
combo_max's 112 surviving targets; the same model is 98.2% over all 168. The gap is the
survivorship effect, not a measurement error.)

---

## 6. Fixed in the 2026-07-29 remediation

Kept rather than deleted so the defect history stays discoverable. Every item below is
landed and covered by tests.

| Defect | Fix | Where |
|---|---|---|
| Off-screen targets auto-scored 0 without querying the model | `status` column; absent targets get `off_screen` and **no** score; analysis restricted to `co_present` | `vlm_eval/runner.py`, `vlm_eval/results.py`, `mcnemar_analysis.py` |
| RTL setting key never read by Android | write `debug.force_rtl` as both setting and system property | `layout_modifier.apply_rtl` |
| Nothing verified a profile applied | read all four vectors back; raise `ProfileVerificationError` | `layout_modifier.verify_profile` |
| RTL mirroring never checked visually | mirror check on captured hierarchy, excluding centred elements | `capture_checks.rtl_applied` |
| Colour transform could silently no-op | before/after diff inside the transform; raises on zero change | `screenshot_pipeline.apply_color_transform` |
| Content drift never measured | baseline-open / baseline-close bracketing per screen | `orchestrator.measure_drift` |
| Missing capture failed silently | completion manifest; run exits non-zero on any gap | `orchestrator.write_manifest` |
| No multiple-comparison correction | Holm–Bonferroni across the family | `vlm_eval/stats.holm_bonferroni` |
| Per-model tests underpowered; targets non-independent | pooled cluster permutation test | `vlm_eval/stats.cluster_permutation_test` |
| No ceiling check (floor check existed) | `Ceiling_Limited` above 95% baseline | `mcnemar_analysis.power_flag` |
| p-values only, no effect sizes | Newcombe paired risk difference + conditional odds ratio | `vlm_eval/stats` |
| Single stochastic draw per query | `VLM_TEMPERATURE=0`, `VLM_TRIALS` majority vote, flip rate | `vlm_provider`, `vlm_eval/runner` |
| Crash discarded ~1000 paid API calls | append + skip completed keys; `--fresh` to restart | `vlm_eval/results.prepare_csv` |
| First `n, n` pair in a reply could be scored | bracket-anchored parse first, loose fallback, method logged | `vlm_eval/scoring` |
| Tree mode leaked 13.1% of targets' names+bounds via `content_desc` fallback, letting the model read the answer off the tree | exclude on the rendered label (full fallback chain), not on `text` alone; re-measured leak rate 0/168 | `vlm_eval/runner.build_tree_text` |

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
- **`play_store` drift.** Its rotating carousel produced 5 of 11 drifted texts in the
  archive. Decide whether to drop the screen once re-collection reports measured drift.
- **`settings_display` self-interference.** Enabling the daltonizer changes the text of
  the Display settings page being measured. Either exclude that screen from the
  colorblind arm or document it.
- **Ferret-UI parse robustness.** 15 unparsed replies in the archive, versus 0–1 for
  hosted models. Its `[[x1,y1,x2,y2]]` regex may not cover every reply shape.

---

## 7. Re-collection checklist

Everything else is done; this is the remaining work, and it needs the emulator.

1. Emulator prerequisites (§8 Conventions): Google account signed in; Messages, Gmail,
   Maps opened once to clear first-run dialogs.
2. `python orchestrator.py --dry-run` — logic path.
3. `python orchestrator.py --screens settings_main` — confirm all four profile
   assertions pass, especially RTL.
4. **Open `dataset/images/settings_main_elder_combo_rtl.png` and confirm by eye that the
   layout is mirrored.** The absence of this check is what caused the original bug.
   Do not skip it because the automated check passed.
5. Full run; confirm the manifest reports no problems and the run exits 0.
6. Evaluate one model first; confirm `status` populates and resume works by interrupting
   and restarting.
7. `python mcnemar_analysis.py --include-rtl` — the flag is only valid once step 4 passes.

If RTL cannot be made to mirror, **drop the arm** and rename the profile to what it
actually is (font 1.5 + density 480). Four honest profiles beat five with one unverified.

---

## 8. Conventions and gotchas

- **Coordinate space.** Labels are shifted into *cropped-image* space: status-bar
  height subtracted from all y values, nav bar removed from the bottom
  (`bound_extractor.extract(y_offset=, bottom_crop=)`). Bar heights come from
  `dumpsys window displays` and **change with density**, so image dimensions differ
  between profiles. Never compare raw y values across profiles without accounting for this.
- **Scoring uses baseline geometry.** `hit_test` builds a box of *baseline* width/height
  (+30 px tolerance per side) centred on the *current* profile's box centre. This keeps
  strictness constant so inflated elements don't become easier to hit by being bigger.
  The `baseline_box=None` branch is a plain bounds check and is only used by tests.
- **Targets come from baseline only** and must appear exactly once there. Duplicated
  text is dropped entirely, which is why 175 baseline texts yield 168 targets.
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
