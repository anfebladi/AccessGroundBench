# AccessGroundBench

AccessGroundBench is a research benchmark that measures how Android accessibility layout changes (large fonts, zoomed displays, RTL layouts, color filters) affect a vision-language model's (VLM) ability to locate UI text elements on screen.

The pipeline has three stages:

1. **Collect** — capture screenshots and UI hierarchy XML from an Android emulator under a baseline layout and five accessibility-stress profiles.
2. **Evaluate** — send grounding queries to a VLM for each captured screen and score the predictions against ground-truth bounding boxes.
3. **Analyze** — compare baseline vs. experimental accuracy using McNemar's paired statistical test.

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
├── layout_modifier.py        # Apply/reset accessibility profiles via ADB settings commands
├── screenshot_pipeline.py    # Capture screenshot + UI XML, crop system bars, color filter
├── bound_extractor.py        # Parse XML → JSON bounding-box label files
├── vlm_evaluator.py          # Entry point: load labels, query VLM, score predictions
├── vlm_provider.py           # LiteLLM + Ferret-UI server calls with retry handling
├── mcnemar_analysis.py       # Paired McNemar's test over evaluation CSVs
├── main.py                   # Minimal package entry point
│
├── vlm_eval/
│   ├── config.py             # VLM model / pacing / retry settings from .env
│   ├── runner.py             # Per-screen evaluation loop and prompt templates
│   ├── targets.py            # Harvest unambiguous text targets from baseline labels
│   ├── scoring.py            # Hit-test logic (point-in-box with ±30 px tolerance)
│   └── results.py            # CSV read/write helpers
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

GOOGLE_API_KEY=your-google-api-key-here
OPENAI_API_KEY=your-openai-api-key-here
ANTHROPIC_API_KEY=your-anthropic-api-key-here
```

Model prefix → required key:
| Model prefix | Key variable |
|---|---|
| `openai/` | `OPENAI_API_KEY` |
| `gemini/` | `GOOGLE_API_KEY` |
| `anthropic/` | `ANTHROPIC_API_KEY` |
| `local/ferret-ui-llama8b` | Ferret-UI server (see below) |

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
| `elder_combo_rtl` | 1.5× | 480 dpi | On | None |
| `colorblind_deuteranomaly` | 1.0× | Default | Off | Deuteranomaly (green-weak) |

> The deuteranomaly color filter is applied in software to the saved PNG (using a 3×3 RGB matrix via Pillow) because `adb screencap` captures display buffers before Android's hardware daltonizer transform is applied.

---

## End-to-End Workflow

### Stage 1 — Collect screenshots and labels

```bash
python orchestrator.py
```

For each of the 13 target screens × 6 profiles the orchestrator will:
- Apply the accessibility profile via ADB settings commands
- Launch the target app and confirm it is in the foreground
- Capture the UI hierarchy XML and screenshot
- Crop system bars (status bar + navigation bar)
- Apply software color filters where required
- Extract interactive text elements to a JSON label file
- Reset the emulator to baseline

**Output:**
```
dataset/images/{screen}_{profile}.png
dataset/raw_xml/{screen}_{profile}.xml
dataset/labels/{screen}_{profile}.json
```

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

---

### Stage 3 — Run McNemar's analysis

```bash
python mcnemar_analysis.py
```

Analyzes all `evaluation_results_*.csv` files in `dataset/` automatically.

To analyze a single file:
```bash
python mcnemar_analysis.py --csv dataset/evaluation_results_openai_gpt-4o-mini.csv
```

For each model and profile, the script:
- Builds a paired contingency table (both-pass, broke-it, fluke-recovery, both-fail)
- Uses asymptotic McNemar's χ² when discordant pairs *n* ≥ 25, exact binomial otherwise
- Flags results as `Floor_Limited` when baseline accuracy < 55%

**Output:** `dataset/mcnemar_results_{model_id}.csv`

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

### `VLM_MODEL` is not set

```bash
# Set temporarily for a single run
VLM_MODEL=openai/gpt-4o-mini python vlm_evaluator.py
```

### McNemar results show `Floor_Limited=Yes`

This means baseline accuracy is below 55%. It is caused by the model failing to ground most elements even under the unmodified baseline layout. Possible causes:
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
- **RTL layout:** `adb shell settings put global force_rtl_layout_direction <0|1>`
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
8. Parse XML → extract interactive nodes with non-empty, non-zero-bounds `text` → save JSON
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

McNemar's paired test over the contingency table for each screen × profile:

| | Exp Pass | Exp Fail |
|---|---|---|
| **Baseline Pass** | *a* | *b* (Broke it) |
| **Baseline Fail** | *c* (Fluke recovery) | *d* |

- *n* = *b* + *c* (discordant pairs)
- *n* ≥ 25 → asymptotic χ² with continuity correction
- *n* < 25 → exact two-tailed binomial (H₀: P(b) = 0.5)
- `Floor_Limited = Yes` when baseline accuracy < 55%
