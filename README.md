# AccessGroundBench

AccessGroundBench is a research benchmark that measures how Android accessibility layout changes (large fonts, zoomed displays, RTL layouts, color filters) affect a vision-language model's (VLM) ability to locate UI text elements on screen.

The pipeline has three stages:

1. **Collect** — capture screenshots and UI hierarchy XML from an Android emulator under a baseline layout and five accessibility-stress profiles.
2. **Evaluate** — send grounding queries to a VLM for each captured screen and score the predictions against ground-truth bounding boxes.
3. **Analyze** — report reachability and grounding separately, using a pooled cluster permutation test plus per-model McNemar tests.

> **Reading results from before 2026-07-29:** the archived run in `dataset/experiment_2/`
> contains three defects that invalidate its headline finding — off-screen targets were
> auto-scored as model failures, the RTL setting never applied, and content drift was
> never measured. See `dataset/experiment_2/README.md`. Those numbers must not be cited.

> **Full mathematics reference:** [`METHODS.md`](METHODS.md) documents every formula in
> this section in detail — plus the two other evaluation modes (accessibility-tree
> injection and cross-file comparison) that aren't covered below — with worked examples
> regenerated from `dataset/experiment_2/` and an explicit statement of what each mode
> can and cannot support.

### Two distinct measurements

The benchmark deliberately keeps these apart, because conflating them inflated an earlier
run's significant results from 4 tests to 24:

- **Reachability** — the share of baseline targets that still *exist* in a modified
  layout. A property of Android under that setting, identical for every model. Large
  fonts at high density push a third of interactive text off the screen entirely.
- **Grounding accuracy** — whether the model can locate a target that *is* on screen.
  Measured only on targets present in both layouts.

A target that scrolled off the screen has not been mislocated by the model; the model was
never asked. Scoring it 0 also penalises accurate models hardest, since a target can only
be counted as "broken" if the model got it right at baseline.

---

## Requirements

| Requirement | Version |
|---|---|
| Python | 3.11 or later |
| Android Studio / AVD | Any recent release |
| Android SDK Platform Tools (`adb`) | Any recent release |
| CUDA-capable GPU *(optional)* | Required only for local Ferret-UI model |

**Python dependencies** (declared in `pyproject.toml`):

```
litellm >= 1.91.3
Pillow >= 10.0
python-dotenv >= 1.0
scipy  (optional — for precise McNemar p-values)
```

Install with `uv` (recommended) or `pip`:

```bash
# using uv
uv sync

# using pip
pip install .

# optional: precise McNemar p-values
pip install scipy
```

---

## Project Layout

```
AccessGroundBench/
├── orchestrator.py           # Master collection driver — runs all screens × profiles
├── app_navigator.py          # Android app launching, permission handling, XML validation
├── adb_utils.py              # Shared ADB helper functions (resolve, run, retry)
├── layout_modifier.py        # Apply/verify/reset accessibility profiles via ADB
├── screenshot_pipeline.py    # Capture screenshot + UI XML, crop system bars, color filter
├── capture_checks.py         # Empirical checks on captured assets (mirroring, drift)
├── bound_extractor.py        # Parse XML → JSON bounding-box label files
├── vlm_evaluator.py          # Entry point: load labels, query VLM, score predictions
├── vlm_provider.py           # LiteLLM + Ferret-UI server calls with retry handling
├── mcnemar_analysis.py       # Reachability, pooled permutation, per-model McNemar
├── main.py                   # Minimal package entry point
│
├── vlm_eval/
│   ├── config.py             # VLM model / pacing / retry / trials settings from .env
│   ├── runner.py             # Per-screen evaluation loop and prompt templates
│   ├── targets.py            # Harvest unambiguous text targets from baseline labels
│   ├── scoring.py            # Coordinate parsing and ±30 px hit-test
│   ├── stats.py              # Statistical primitives (permutation, Holm, CIs)
│   └── results.py            # CSV read/write, resume support
│
├── ferret_ui/                # Local Ferret-UI inference server (optional)
│   ├── ferret_server.py      # FastAPI server wrapping the Ferret-UI model
│   ├── start_server.bat      # Launch script for Windows
│   ├── requirements.txt      # Ferret-UI Python dependencies (separate venv)
│   └── ...                   # Model architecture modules
│
├── dataset/
│   ├── images/               # Collected PNGs  — gitignored, created by orchestrator
│   ├── raw_xml/              # Collected UI XML — gitignored, created by orchestrator
│   ├── labels/               # Extracted JSON labels — gitignored, created by orchestrator
│   └── experiment_1/         # Committed reference results from Experiment 1
│
├── tests/                    # Unit tests
├── outputs/                  # Standalone pipeline output (gitignored)
├── .env.example              # Environment variable template — copy to .env
├── .python-version           # Python version pin
└── pyproject.toml            # Project metadata and dependencies
```

---

## Setup

### Step 1 — Clone the repository

```bash
git clone <repo-url>
cd AccessGroundBench
```

### Step 2 — Install Python dependencies

```bash
uv sync
# or: pip install .
```

### Step 3 — Configure environment variables

Copy the template and fill in your API keys:

```bash
cp .env.example .env
```

Edit `.env`:

```dotenv
# Comma-separated list of models to evaluate (evaluated in sequence)
VLM_MODEL=openai/gpt-4o-mini, gemini/gemini-2.5-pro, local/ferret-ui-llama8b

VLM_PACE_SECONDS=0       # Optional delay between API calls (use for rate-limited APIs)
VLM_MAX_RETRIES=3         # Number of retries on provider failure
VLM_REQUEST_TIMEOUT_SECONDS=120  # Per-request timeout in seconds

GOOGLE_API_KEY=your-google-api-key-here
OPENAI_API_KEY=your-openai-api-key-here
ANTHROPIC_API_KEY=your-anthropic-api-key-here

# Optional: local 9Router using Codex/other subscription quota
NINEROUTER_BASE_URL=http://localhost:20128/v1
NINEROUTER_API_KEY=your-9router-api-key-here

# Optional: any other OpenAI-compatible gateway
OPENAI_COMPATIBLE_BASE_URL=https://provider.example.com/v1
OPENAI_COMPATIBLE_API_KEY=your-compatible-provider-key-here
```

Model prefix → required key:
| Model prefix | Key variable |
|---|---|
| `openai/` | `OPENAI_API_KEY` |
| `gemini/` | `GOOGLE_API_KEY` |
| `anthropic/` | `ANTHROPIC_API_KEY` |
| `local/ferret-ui-llama8b` | Ferret-UI server (see below) |
| `9router/` | `NINEROUTER_BASE_URL` + `NINEROUTER_API_KEY` |
| `openai_compatible/` | `OPENAI_COMPATIBLE_BASE_URL` + `OPENAI_COMPATIBLE_API_KEY` |

Hosted models are sent through LiteLLM. Native LiteLLM model names keep their
normal behavior. For 9Router, connect your provider in the 9Router dashboard,
then select the route in `.env`:

```dotenv
VLM_MODEL=9router/cx/gpt-5.3-codex
NINEROUTER_BASE_URL=http://localhost:20128/v1
NINEROUTER_API_KEY=your-9router-api-key
```

The `9router/` prefix is translated to an OpenAI-compatible LiteLLM request;
the route after the prefix is passed through unchanged. You can use the same
adapter with another OpenAI-compatible gateway:

```dotenv
VLM_MODEL=openai_compatible/provider/model-name
OPENAI_COMPATIBLE_BASE_URL=https://provider.example.com/v1
OPENAI_COMPATIBLE_API_KEY=your-provider-key
```

The base URL may include `/v1` or omit it. One generic compatibility endpoint
is configured per process, while native providers can still be mixed in the
comma-separated `VLM_MODEL` list.

Compatibility requests time out after 120 seconds by default and retry
transient timeout, connection, and rate-limit failures according to
`VLM_MAX_RETRIES`. Adjust `VLM_REQUEST_TIMEOUT_SECONDS` for slower gateways.

### Step 4 — Set up the Android emulator

1. Open **Android Studio** → **Device Manager** → **Create Virtual Device**
2. Select hardware profile: **Pixel 6**
3. Select system image: **Android 14 (API 34), x86_64**
4. Start the AVD and wait for it to fully boot
5. Verify ADB sees it:

```bash
adb devices
# Expected output:
# List of devices attached
# emulator-5554   device
```

> **Windows note:** If `adb` is not on PATH, use the full path:
> `C:\Users\<you>\AppData\Local\Android\Sdk\platform-tools\adb.exe`

### Step 5 — Prepare the emulator

Some apps require a one-time manual setup before the orchestrator can navigate to them automatically:

1. **Sign in with a Google Account** — open the Play Store app and sign in. This unlocks Gmail, YouTube, Maps, and Photos automatically.
2. **Dismiss first-run dialogs** — manually open each of the following apps once and tap through any welcome screens or permission dialogs:
   - Messages
   - Gmail
   - Google Maps
3. Verify the emulator is back on the home screen before running the orchestrator.

---

## Accessibility Profiles

Six layout profiles are applied programmatically to the emulator before each screen capture:

| Profile | Font Scale | Screen Density | Force RTL | Color Filter |
|---|---:|---|---|---|
| `baseline` | 1.0× | Device default | Off | None |
| `elder_text_heavy` | 1.4× | Default | Off | None |
| `elder_zoom_heavy` | 1.0× | 480 dpi | Off | None |
| `elder_combo_max` | 1.6× | 520 dpi | Off | None |
| `elder_combo_mid` | 1.5× | 480 dpi | Off | None |
| `colorblind_deuteranomaly` | 1.0× | Default | Off | Deuteranomaly (green-weak) |

> The deuteranomaly color filter is applied in software to the saved PNG (using a 3×3 RGB matrix via Pillow) because `adb screencap` captures display buffers before Android's hardware daltonizer transform is applied.

> `elder_combo_mid` was `elder_combo_rtl` (Force RTL on) until re-collection measured
> 0% mirroring across every screen, even with the corrected setting key. The RTL arm
> was dropped rather than kept unverified; no profile requests RTL anymore.

### Profile verification

Every profile is read back from the device after it is applied
(`layout_modifier.verify_profile`), and a mismatch aborts that capture rather than
producing data that measures the wrong condition. Profiles with a visible signature are
additionally checked against the captured assets:

- **RTL** — the captured hierarchy is compared with the geometry-matched non-RTL profile;
  at least half of the shared off-centre text elements must appear at their mirrored x
  position. Elements within 150 px of the screen midline are excluded, since mirroring
  maps them onto themselves.
- **Colour** — verified inside `apply_color_transform` by diffing the image before and
  after the matrix is applied, which is exact and immune to content drift.

This exists because an earlier run wrote `development_settings_force_rtl`, a key Android
does not read. Nothing checked, so the entire RTL arm was silently a font-and-density
condition. The mirror check flags all 13 of those archived captures.

**RTL setting key:** the developer "Force RTL layout direction" toggle is
`Settings.Global.DEVELOPMENT_FORCE_RTL`, whose value is `debug.force_rtl`. Both the
global setting and the matching system property must be written:

```bash
adb shell settings put global debug.force_rtl 1
adb shell setprop debug.force_rtl 1
```

---

## End-to-End Workflow

### Stage 1 — Collect screenshots and labels

```bash
python orchestrator.py
```

For each of the 13 target screens the orchestrator captures **7 assets** — an opening
baseline, the 5 experimental profiles, then a closing baseline — and for each one will:
- Apply the accessibility profile via ADB settings commands
- Verify all four display vectors read back correctly from the device
- Launch the target app and confirm it is in the foreground
- Capture the UI hierarchy XML and screenshot
- Crop system bars (status bar + navigation bar)
- Apply software color filters where required
- Extract text elements to a JSON label file
- Reset the emulator to baseline

**Baseline bracketing.** The opening and closing baselines are captured minutes apart
around the same screen, so diffing them measures how much the app changed its own content
during the sweep. That per-screen **drift rate** is the empirical noise floor: an effect
smaller than the drift cannot be told apart from a rotating carousel or a ticking clock.
Screens exceeding 5% drift are flagged in the manifest. The archived run captured
baselines days from their comparison profiles and never measured this, leaving 6.3% drift
mixed into every result.

**Output:**
```
dataset/images/{screen}_{profile}.png
dataset/raw_xml/{screen}_{profile}.xml
dataset/labels/{screen}_{profile}.json
dataset/collection_manifest.json
```

The manifest lists every expected versus actual capture, each profile's verification
result, and per-screen drift. **The run exits non-zero if anything is missing or
unverified** — an earlier run lost `photos_elder_text_heavy` to a caught-and-ignored
exception, shrinking that profile from 168 to 165 targets with nothing in the output to
say so.

**Dry run (no emulator needed):**
```bash
python orchestrator.py --dry-run
```

**Collect specific screens only:**
```bash
python orchestrator.py --screens settings_main contacts dialer
```

> **Target apps:** `settings_main`, `settings_display`, `settings_network`, `settings_accessibility`, `contacts`, `dialer`, `messages`, `clock`, `maps`, `play_store`, `gmail`, `youtube`, `photos`

---

### Stage 2 — Run VLM evaluation

```bash
python vlm_evaluator.py
```

The evaluator:
1. Discovers all screens from `dataset/labels/*_baseline.json`
2. Harvests unambiguous text targets (unique text on screen, appears exactly once)
3. Queries each configured VLM with a grounding prompt for every `(target, screen, profile)` triple
4. Scores each prediction with a ±30 px hit-test against the ground-truth bounding box
5. Writes results to CSV

**Output:** `dataset/evaluation_results_{model_id}.csv`

Example: `VLM_MODEL=openai/gpt-4o-mini` → `dataset/evaluation_results_openai_gpt-4o-mini.csv`

**Row status.** Every row carries a `status`, and only `co_present` rows have a score:

| Status | Meaning |
|---|---|
| `co_present` | Target exists in both layouts; the model was queried and scored |
| `off_screen` | Target absent from this layout — no measurement, **not** a failure |
| `api_error` | Provider failed; the row is retried on resume rather than scored |

**Resume.** Runs append and skip already-completed `(screen, target, profile)` keys, so an
interrupted run does not discard ~1000 paid API calls. Use `--fresh` to start over.

**Determinism.** `VLM_TEMPERATURE` defaults to 0. Set `VLM_TRIALS=3` to send each query
three times and score by majority vote; the run then reports a **flip rate**, letting you
answer "how do you know this isn't sampling noise?" with a measurement. Repeats do not
add statistical power. `VLM_TRIALS_MODELS` restricts repeats to specific models.

---

### Stage 3 — Run statistical analysis

```bash
python mcnemar_analysis.py
```

Analyzes all `evaluation_results_*.csv` files in `dataset/` automatically.

```bash
python mcnemar_analysis.py --csv dataset/evaluation_results_openai_gpt-4o-mini.csv
python mcnemar_analysis.py --data-dir dataset/experiment_2   # re-analyse the archive
```

The script reports four sections:

**1. Reachability** — `targets_present / targets_baseline` per profile, with Wilson
confidence intervals. Model-independent, no hypothesis test needed.

**2. Grounding, pooled across models (primary)** — a cluster permutation test per profile.

**3. Grounding, per model (secondary)** — McNemar on co-present rows only, with
Holm–Bonferroni across the whole family, plus power flags.

**4. Direction consistency** — a sign test over how many models degraded, as descriptive
corroboration that a pooled effect is not driven by one model.

**Output:** `reachability_results.csv`, `pooled_permutation_results.csv`,
`mcnemar_results_per_model.csv`, `direction_consistency.csv`

`elder_combo_rtl` (the archived RTL arm, `dataset/experiment_2/`) was renamed
`elder_combo_mid` and folded into the default profile set — see the profile table above.

---

## Optional: Local Ferret-UI Model

Ferret-UI is a small open-source VLM fine-tuned for mobile UI grounding. It runs locally on a CUDA-capable GPU.

### Setup

1. Download the model weights (requires Hugging Face access):

```bash
python ferret_ui/download_scripts.py
```

2. Create a separate virtual environment for Ferret-UI (its dependencies conflict with the main project):

```bash
cd ferret_ui
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

3. Start the inference server:

```bash
.\ferret_ui\start_server.bat
```

The server runs on `http://localhost:8000` by default. Leave it running in a separate terminal.

4. Add `local/ferret-ui-llama8b` to `VLM_MODEL` in `.env` and run the evaluator normally.

> **Hardware:** Running Ferret-UI requires a CUDA GPU with at least 10 GB VRAM. The model will not damage hardware — the GPU will thermal-throttle or OOM-error safely if resources are insufficient.

---

## Standalone Utilities

The collection tools can be run independently when an emulator is connected:

```bash
# Apply an accessibility profile manually
python layout_modifier.py elder_combo_max

# Reset emulator to baseline
python layout_modifier.py reset

# Capture a single screen (output goes to outputs/)
python screenshot_pipeline.py my_capture

# Extract labels from a single XML file
python bound_extractor.py outputs/my_capture.xml
```

---

## Troubleshooting

### `adb devices` shows no device

- Make sure the AVD is fully booted (home screen visible)
- On Windows, confirm the Platform Tools path is correct or add it to PATH
- If the emulator disconnected after a script crash, run: `adb kill-server && adb start-server`

### Orchestrator freezes without output

The `uiautomator dump` command hangs when a system popup is covering the screen. The script is designed to time out after 15 seconds and skip the frozen capture automatically. If it consistently freezes on a particular screen, manually dismiss any system dialogs on the emulator.

### `ERROR: null root node returned by UiTestAutomationBridge`

The app had not finished rendering when `uiautomator dump` was called. The orchestrator retries automatically. If this persists, try increasing `SETTLE_DELAY` in `layout_modifier.py`.

### Evaluator reports no screens found

No baseline label files exist in `dataset/labels/`. Run `python orchestrator.py` first to collect the dataset.

### Model key is missing

Set the correct key in `.env`. Values that still contain `your-...-here` are treated as unset. Check that the `VLM_MODEL` prefix matches the provider key variable (see the table in Setup Step 3).

For 9Router, confirm the local router is running and that
`NINEROUTER_BASE_URL` points to its OpenAI-compatible `/v1` endpoint. For
other compatible gateways, set both `OPENAI_COMPATIBLE_BASE_URL` and
`OPENAI_COMPATIBLE_API_KEY`.

### `VLM_MODEL` is not set

```bash
# Set temporarily for a single run
VLM_MODEL=openai/gpt-4o-mini python vlm_evaluator.py
```

### Analysis shows a `floor` or `ceiling` power flag

Both mean the comparison cannot detect degradation, so its p-value says nothing either way.

**`ceiling`** — baseline accuracy above 95%. Almost every target already passes, so there
is nothing left to break. Report as underpowered, never as resilience. This is the normal
state for frontier models on this benchmark and is not a bug.

**`floor`** — baseline accuracy below 50%. The model fails to ground most elements even
under the unmodified baseline layout. Possible causes:
- Prompt format mismatch (especially for Ferret-UI — it requires its specific training prompt)
- Model has no vision capability
- Bounding boxes are too small relative to model prediction precision (increase `TOLERANCE` in `vlm_eval/scoring.py`)

---

## Methods

This section describes the full experimental methodology in sufficient detail for replication.

### Overview

The benchmark evaluates whether Android accessibility layout transformations impair a VLM's ability to ground UI text elements. Each experiment follows a paired design: the same model receives the same grounding queries under a **baseline** layout and under each **experimental accessibility profile**, and the resulting hit-rate difference is evaluated using McNemar's test.

### 1. Environment Setup

- **Host:** Windows 11, Android Studio
- **Emulator:** AVD running Android 14 (API 34), Pixel 6 hardware profile, x86_64 system image, 1080 × 2400 px screen (420 dpi)
- **Python:** 3.11, dependencies as listed above
- All target applications were pre-launched manually once to dismiss first-run onboarding dialogs
- Google Account sign-in was completed on the emulator to unlock apps requiring authentication

### 2. Target Applications

13 Android apps were used. Apps requiring unavailable hardware (Camera), apps not installed by default (Files), and apps that failed to reliably launch on the test emulator (Chrome) were excluded.

### 3. Accessibility Profiles

Six profiles were applied via ADB `settings` commands:

- **Font scale:** `adb shell settings put system font_scale <value>`
- **Screen density:** `adb shell wm density <value>` / `wm density reset`
- **RTL layout:** `adb shell settings put global debug.force_rtl <0|1>` plus
  `adb shell setprop debug.force_rtl <0|1>` — this is `Settings.Global.DEVELOPMENT_FORCE_RTL`.
  Writing the setting without the system property does not trigger a reflow.
- **Color filter:** Android's daltonizer toggled via `accessibility_display_daltonizer_enabled` and `accessibility_display_daltonizer` secure settings. Applied in software to the PNG because `adb screencap` captures pre-daltonizer buffers.
- A 2.5-second stabilization delay followed each profile application.

### 4. Data Collection Pipeline

For each screen × profile pair:

1. Apply profile → 2.5 s settle
2. Launch app via `adb shell am start`; confirm foreground package; auto-dismiss permission dialogs
3. `adb shell uiautomator dump` with 15-second timeout (retried 3× on failure/timeout)
4. `adb shell screencap` immediately after XML dump
5. `adb pull` both files to host
6. Crop status bar and navigation bar heights (detected from `dumpsys window displays`)
7. Apply software deuteranomaly matrix (colorblind profile only)
8. Parse XML → extract every node with non-empty, non-zero-bounds `text`, excluding
   full-screen containers → save JSON. Note this is not filtered by clickability: the
   benchmark grounds text, not only interactive controls.
9. Reset all four display vectors to baseline

### 5. Target Harvesting

From each `{screen}_baseline.json`:
- Include only elements with non-empty, non-whitespace `text`
- Include only elements whose `text` value appears **exactly once** on screen (discard duplicates)
- The same target set is used for all profiles of that screen

### 6. VLM Evaluation

**General-purpose models (GPT, Gemini, Claude):**
```
You are an autonomous mobile agent operating an Android phone.
Look closely at this image and find the UI element with the text '{target_text}'.
Provide the exact central pixel (x,y) coordinates of that element.
Return your response strictly in the bracket format: [x, y]
```

**Ferret-UI only:**
```
Provide the bounding box of the text '{target_text}'.
```

Ferret-UI was fine-tuned on this exact format. The general-purpose prompt caused it to return text descriptions instead of coordinates.

**Scoring:** A prediction is a hit (1) if the predicted (x, y) falls within the target element's bounding box expanded by ±30 px on all sides (simulating Google's 48 dp minimum touch-target guideline). All results logged to `evaluation_results_{model}.csv`.

### 7. Statistical Analysis

All grounding tests are restricted to **co-present** targets. Off-screen targets are
reported separately as reachability.

#### 7.1 Reachability

Per profile, the share of baseline targets still present in the modified layout, with a
**Wilson score interval**. Wilson rather than Wald because the benchmark operates near the
boundary (baseline accuracies of 98–99%), where Wald intervals run outside [0, 1].

#### 7.2 Pooled cluster permutation test (primary)

Per profile, pooled across models. The statistic is net degradation
*T* = Σ(baseline − experimental) over every target × model. The null distribution is built
by randomly flipping each **target cluster** — all of that target's outcomes across every
model, relabelled together — 20,000 times and recomputing *T*. The p-value is the share of
shuffles reaching |*T*| as extreme as observed, computed as (count + 1)/(*n* + 1) since the
observed labelling is itself one of the equally likely permutations.

Two reasons this replaces per-model McNemar as the primary test:

1. **Power.** The smallest achievable two-tailed exact binomial p-value is 2·0.5ⁿ, so
   after Holm correction across ~28 tests a model needs ≥ 11 one-directional discordant
   pairs to reach significance. Several models cannot produce that even in principle —
   one has *b* = 0, *c* = 0 on a profile. Pooling supplies enough discordant observations
   to test at all.
2. **Non-independence.** The same targets are reused for every model, so a target's
   per-model outcomes are correlated: an intrinsically hard target is hard for everyone.
   Pooling into one large McNemar would treat those as independent and manufacture
   confidence. Permuting whole clusters preserves the correlation exactly.

A permutation test is preferred to a logistic mixed model here because it adds no
distributional assumptions (link function, normally distributed random effects) and needs
only numpy/scipy. The RNG seed is fixed for reproducibility.

**Estimand:** this tests whether a profile degrades grounding *averaged over the models
evaluated*. It does not model per-model differences — §7.3 does.

#### 7.3 Per-model McNemar (secondary)

Contingency table per model × profile:

| | Exp Pass | Exp Fail |
|---|---|---|
| **Baseline Pass** | *a* | *b* (Broke it) |
| **Baseline Fail** | *c* (Fluke recovery) | *d* |

- *n* = *b* + *c* (discordant pairs)
- *n* ≥ 25 → asymptotic χ² with Edwards' continuity correction
- *n* < 25 → exact two-tailed binomial (H₀: P(b) = 0.5)
- **Holm–Bonferroni** across the whole family. Holm is uniformly more powerful than plain
  Bonferroni at the same family-wise error rate and, unlike Benjamini–Hochberg, assumes no
  independence — these tests share data.

**Power flags.** A comparison is marked `floor` when baseline accuracy < 50% and `ceiling`
when it exceeds 95%. Both mean the test is uninformative rather than negative: at 99%
baseline there is almost nothing left to break, so a null result is **underpowered, not
evidence of resilience**. The ceiling flag mirrors the floor flag, which earlier revisions
had only at the bottom of the scale.

#### 7.4 Effect sizes

p-values state whether an effect exists, not how large it is. Each comparison also reports:

- **Risk difference** (baseline − experimental accuracy) with a **Newcombe method-10**
  interval. Newcombe rather than an unpaired interval because both arms share the same
  targets and are correlated, so an unpaired interval would be too wide.
- **Conditional odds ratio** *b*/*c* with an exact Clopper–Pearson-derived interval. An
  odds ratio of 2 means a target was twice as likely to break as to recover.

#### 7.5 Direction consistency (descriptive)

A two-tailed sign test over how many models degraded under each profile. Reported as
corroboration only — models are not a random sample of a population, so this checks that a
pooled effect is consistent rather than driven by one model, and is not an independent
inferential claim.

#### 7.6 Content drift

The symmetric difference of text sets between a screen's opening and closing baselines,
as a share of baseline texts. This is the empirical noise floor; effects below it are not
interpretable.

#### 7.7 Other evaluation modes

Sections 7.1–7.6 describe the vision-only mode (`USE_A11Y_TREE=false`, the default).
AccessGroundBench also supports **accessibility-tree injection**
(`USE_A11Y_TREE=true`, prompts the model with a partial a11y tree alongside the image)
and **cross-file comparison** (`mcnemar_analysis.py --compare-a --compare-b`, typically
used to compare a vision-only run against a tree-injected run of the same model).

The same machinery in 7.1–7.5 applies to tree-injected results unchanged, run against
`evaluation_results_{model}_with_tree.csv`. Cross-file comparison currently applies only
a plain McNemar test with no Holm correction, no floor/ceiling flags, and no effect
sizes — and it does not test whether the tree *protects* against a profile's
degradation, since that is an interaction (difference-in-differences) that is not yet
implemented.

See [`METHODS.md`](METHODS.md) for the complete treatment of both modes, including the
tree's target-exclusion mechanism (and a leak in it that was found and fixed on
2026-07-29), what reachability means when a tree is injected, and the interaction test
recommended for a future cross-file comparison.
