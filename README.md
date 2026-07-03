# AccessGroundBench

AccessGroundBench is an Android UI evaluation framework that measures how
accessibility layout modifications affect Vision Language Model (VLM) spatial
grounding accuracy.

The pipeline has four phases:

1. **Data Collection** (`orchestrator.py`): Capture screenshots and UI
   hierarchies across multiple accessibility profiles via an Android emulator.
2. **VLM Evaluation** (`vlm_evaluator.py`): Send images to Gemini and
   evaluate grounding accuracy via bounding-box hit-testing.
3. **Statistical Analysis** (`mcnemar_analysis.py`): Run McNemar's test to
   determine whether layout distortions cause statistically significant
   performance degradation.

## Directory structure

```text
AccessGroundBench/
├── orchestrator.py          # Phase 1 — master data-collection driver
├── vlm_evaluator.py         # Phase 2 — VLM grounding + hit-test scoring
├── mcnemar_analysis.py      # Phase 3 — McNemar's statistical analysis
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
- `vlm_evaluator.py` — Offline evaluation engine that harvests targets from
  baseline labels, calls Gemini with grounding prompts, parses coordinates,
  and logs hit-test scores to CSV.
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
- `google-genai` Python package (for VLM evaluation)
- `scipy` Python package (for statistical analysis, optional but recommended)

Install dependencies:

```bash
pip install google-genai scipy
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
- Prompt you to navigate the emulator to each target screen
- Apply all 5 accessibility profiles
- Capture screenshots and UI hierarchies
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

Set your Gemini API key:

```bash
set GOOGLE_API_KEY=your-key-here
```

Run the evaluator:

```bash
python vlm_evaluator.py
```

Options:

```bash
python vlm_evaluator.py --model gemini-2.5-pro
python vlm_evaluator.py --screens settings_main
```

The evaluator automatically:
- Harvests text targets from baseline labels
- Detects off-screen elements (immediate failure)
- Rate-limits API calls to 5/minute (12s delay)
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

### `google-genai not installed`

```bash
pip install google-genai
```

### `GOOGLE_API_KEY not set`

```bash
set GOOGLE_API_KEY=your-key-here
```

### `scipy not installed`

McNemar's analysis works without scipy (using fallback calculations) but
precise p-values require it:

```bash
pip install scipy
```
