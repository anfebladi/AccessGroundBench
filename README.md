# AccessGroundBench

AccessGroundBench is an Android UI evaluation framework that measures how
accessibility layout modifications affect Vision Language Model (VLM) spatial
grounding accuracy.

The pipeline has four phases:

1. **Data Collection** (`orchestrator.py`): Capture screenshots and UI
   hierarchies across multiple accessibility profiles via an Android emulator.
2. **VLM Evaluation** (`vlm_evaluator.py`): Send images to LiteLLM-supported
   vision models and evaluate grounding accuracy via bounding-box hit-testing.
3. **Statistical Analysis** (`mcnemar_analysis.py`): Run McNemar's test to
   determine whether layout distortions cause statistically significant
   performance degradation.

## Directory structure

```text
AccessGroundBench/
├── orchestrator.py          # Phase 1 — master data-collection driver
├── vlm_evaluator.py         # Phase 2 — VLM grounding + hit-test scoring
├── mcnemar_analysis.py      # Phase 3 — McNemar's statistical analysis
├── app_navigator.py         # ADB app launcher/foreground validator
├── adb_utils.py             # Shared ADB path/device/command helpers
├── screenshot_pipeline.py   # ADB capture utility (used by orchestrator)
├── layout_modifier.py       # Accessibility profile injector (used by orchestrator)
├── bound_extractor.py       # XML → JSON bounding-box extractor (used by orchestrator)
├── dataset/
│   ├── images/              # Finalized screenshots ({screen}_{profile}.png)
│   ├── raw_xml/             # Raw UI hierarchy dumps ({screen}_{profile}.xml)
│   ├── labels/              # Parsed JSON bounding boxes ({screen}_{profile}.json)
│   └── evaluation_results.csv  # Master evaluation ledger
├── outputs/                 # Legacy capture output directory
└── sample_input/            # Committed sample/reference inputs
```

## What each script does

- `orchestrator.py` — Master driver that iterates through target screens and
  accessibility profiles, automating the capture/extraction loop.
- `app_navigator.py` — Launches each target Android app/screen through ADB and
  validates the foreground package before capture.
- `adb_utils.py` — Shared helper functions for resolving ADB, selecting the
  active emulator, and running device-scoped ADB commands.
- `vlm_evaluator.py` — Offline evaluation engine that harvests targets from
  baseline labels, calls LiteLLM-supported vision models with grounding
  prompts, parses coordinates, and logs hit-test scores to CSV.
- `mcnemar_analysis.py` — Statistical analysis that builds paired contingency
  matrices and runs McNemar's test (asymptotic or exact binomial).
- `screenshot_pipeline.py` — Captures the active emulator screen as a `.png`
  and dumps the Android UI hierarchy as a matching `.xml` file.
- `layout_modifier.py` — Applies accessibility stress profiles to the emulator,
  including larger text, density changes, and RTL layout.
- `bound_extractor.py` — Converts one captured XML hierarchy into cleaned JSON
  bounding-box records.

## Accessibility profiles

| Profile            | Font Scale | Density | RTL |
|--------------------|-----------|---------|-----|
| `baseline`         | 1.0       | reset   | off |
| `elder_text_heavy` | 1.4       | reset   | off |
| `elder_zoom_heavy` | 1.0       | 480     | off |
| `elder_combo_max`  | 1.6       | 520     | off |
| `elder_combo_rtl`  | 1.5       | 480     | on  |

## Prerequisites

- Python 3.10+
- Android Studio with an Android Virtual Device (AVD)
- Android SDK Platform Tools (`adb`)
- `litellm` Python package (for VLM evaluation)
- `scipy` Python package (for statistical analysis, optional but recommended)

Install dependencies:

```bash
pip install litellm scipy
```

## Set up ADB on Windows

First, check whether `adb` is already available:

```bash
adb devices
```

The scripts automatically resolve `adb.exe` from `%LOCALAPPDATA%\Android\Sdk\platform-tools\`.
If that path doesn't exist, ensure `adb` is on your system `PATH`.

For macOS:

```bash
export PATH="$HOME/Library/Android/sdk/platform-tools:$PATH"
```

## Start an emulator

1. Open Android Studio.
2. Go to `Tools > Device Manager`.
3. Create a virtual device if you do not already have one.
4. Start the virtual device.
5. Wait until Android fully boots to the home screen.
6. Verify:

```bash
adb devices
```

Expected output:

```text
List of devices attached
emulator-5554    device
```

## Full end-to-end workflow

### Phase 1: Data collection

```bash
python orchestrator.py
```

The script will:
- Iterate through the predefined screen list
- Apply all 5 accessibility profiles
- Automatically launch and validate each target app before capture
- Capture screenshots and UI hierarchies
- Abort if the captured XML belongs to the wrong app
- Extract bounding-box labels
- Reset the emulator after each screen

To validate the pipeline without an emulator:

```bash
python orchestrator.py --dry-run
```

To run specific screens:

```bash
python orchestrator.py --screens settings_main contacts
```

### Phase 2: VLM evaluation

Set the model and API key for the direct provider model you want to run:

```bash
export VLM_MODEL=openai/gpt-4o-mini
export VLM_PACE_SECONDS=0.5
export VLM_MAX_RETRIES=3
export GOOGLE_API_KEY=your-key-here
export OPENAI_API_KEY=your-key-here
export ANTHROPIC_API_KEY=your-key-here
```

Run the evaluator:

```bash
python vlm_evaluator.py
```

Options:

```bash
# Temporary model overrides if VLM_MODEL is not set or you want to switch models
python vlm_evaluator.py --model openai/gpt-4o-mini
python vlm_evaluator.py --model gemini/gemini-2.5-pro
python vlm_evaluator.py --model anthropic/claude-3-5-sonnet-latest
python vlm_evaluator.py --pace-seconds 0.5
python vlm_evaluator.py --screens settings_main
```

The evaluator automatically:
- Harvests text targets from baseline labels
- Detects off-screen elements (immediate failure)
- Retries provider rate limits, with optional pacing via `VLM_PACE_SECONDS`
- Hit-tests predictions against ground-truth bounding boxes
- Logs all results to `dataset/evaluation_results.csv`

### Phase 3: Statistical analysis

```bash
python mcnemar_analysis.py
```

Options:

```bash
python mcnemar_analysis.py --csv path/to/results.csv
```

The analysis:
- Pairs each element's baseline and experimental scores
- Builds 2×2 contingency matrices per profile
- Selects asymptotic McNemar (b+c ≥ 25) or exact binomial (b+c < 25)
- Reports p-values against α=0.05

## Legacy workflow

The individual utility scripts still work standalone:

```bash
python layout_modifier.py elder_combo_max
python screenshot_pipeline.py my_capture
python layout_modifier.py reset
python bound_extractor.py outputs/my_capture.xml
```

## Troubleshooting

### `No devices found`

No emulator is connected. Start one from Android Studio `Tools > Device Manager`.

### `litellm not installed`

```bash
pip install litellm
```

### Provider API key not set

```bash
export VLM_MODEL=openai/gpt-4o-mini
export VLM_PACE_SECONDS=0.5
export VLM_MAX_RETRIES=3
export GOOGLE_API_KEY=your-key-here
export OPENAI_API_KEY=your-key-here
export ANTHROPIC_API_KEY=your-key-here
```

### `VLM_MODEL not set`

Set a LiteLLM model string in `.env` or pass `--model`:

```bash
export VLM_MODEL=openai/gpt-4o-mini
python vlm_evaluator.py --model openai/gpt-4o-mini
```

### OpenAI rate limit errors

Use a small optional delay between successful calls:

```bash
export VLM_PACE_SECONDS=0.5
python vlm_evaluator.py --pace-seconds 0.5
```

### `scipy not installed`

McNemar's analysis works without scipy (using fallback calculations) but
precise p-values require it:

```bash
pip install scipy
```
