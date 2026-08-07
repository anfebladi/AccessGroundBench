# AccessGroundBench

AccessGroundBench evaluates how Android accessibility-layout changes affect a
vision-language model's ability to locate UI elements. It has three stages:

1. Capture a target Android screen under a baseline and accessibility-stress
   profiles.
2. Evaluate saved screenshots and labels with a LiteLLM-supported vision model.
3. Compare each experimental profile with baseline accuracy using McNemar's
   test.

## Requirements

- Python 3.11 or later
- An Android emulator (AVD) running a supported target app
- Android SDK Platform Tools (`adb`) available on `PATH`
- A provider API key for the model used during VLM evaluation

The project dependencies are declared in `pyproject.toml`:

- `litellm`
- `Pillow`
- `python-dotenv`

Install them with your preferred environment manager. For example:

```bash
uv sync
# or
python -m pip install .
```

SciPy is optional. The analysis script works without it using fallback
calculations, but SciPy provides the precise McNemar p-values:

```bash
python -m pip install scipy
```

## Project layout

```text
AccessGroundBench/
├── .env.example             # Model configuration and provider-key template
├── .python-version          # Project Python version pin
├── pyproject.toml           # Project metadata and dependencies
├── uv.lock                  # Locked dependency set
├── main.py                  # Minimal package entry point
├── orchestrator.py          # Android data-collection driver
├── app_navigator.py         # Android screen launch and validation
├── adb_utils.py             # Shared ADB helpers
├── layout_modifier.py       # Accessibility-profile applicator
├── screenshot_pipeline.py   # Screenshot and UI-hierarchy capture
├── bound_extractor.py       # XML-to-JSON bounding-box extraction
├── vlm_evaluator.py         # Offline VLM evaluation entry point
├── vlm_provider.py          # LiteLLM calls and retry handling
├── vlm_eval/                # Evaluation config, targets, scoring, results, runner
├── rescore_coords.py        # Offline re-scoring under a different coord space
├── mcnemar_analysis.py      # Paired statistical analysis
├── tests/                   # Unit tests
├── sample_input/            # Committed PNG/XML sample captures
├── outputs/                 # Ignored standalone-capture output directory
└── dataset/
    ├── images/              # Ignored collected PNGs; .gitkeep is committed
    ├── raw_xml/             # Ignored collected XML; .gitkeep is committed
    ├── labels/              # Ignored extracted labels; .gitkeep is committed
    ├── evaluation_results_*.csv  # Evaluation ledgers
    └── mcnemar_results_*.csv     # Analysis reports
```

The collection pipeline writes screenshots, XML, and labels under `dataset/`.
Those capture artifacts are intentionally ignored by Git (apart from the
directory placeholders). Evaluation reads them from disk and does not control
the emulator.

## Accessibility profiles

| Profile | Font scale | Density | Force RTL |
| --- | ---: | --- | --- |
| `baseline` | 1.0 | reset | off |
| `elder_text_heavy` | 1.4 | reset | off |
| `elder_zoom_heavy` | 1.0 | 480 | off |
| `elder_combo_max` | 1.6 | 520 | off |
| `elder_combo_rtl` | 1.5 | 480 | on |

## Setup

### Connect an emulator

Start an AVD from Android Studio's Device Manager, wait for it to boot, then
confirm that ADB sees exactly one usable device:

```bash
adb devices
```

On macOS, a typical SDK Platform Tools location is
`$HOME/Library/Android/sdk/platform-tools`. Add it to `PATH` if needed:

```bash
export PATH="$HOME/Library/Android/sdk/platform-tools:$PATH"
```

### Configure a VLM provider

Copy `.env.example` to `.env` and replace the placeholder key for the selected
provider. `vlm_evaluator.py` loads `.env` automatically.

```bash
cp .env.example .env
```

At minimum, configure `VLM_MODEL` and the matching key. The evaluator supports
these variables:

```dotenv
VLM_MODEL=openai/gpt-4o-mini
VLM_PACE_SECONDS=0
VLM_MAX_RETRIES=3
COORD_SPACE=pixel

OPENAI_API_KEY=your-openai-api-key
GOOGLE_API_KEY=your-google-api-key
GEMINI_API_KEY=your-gemini-api-key
ANTHROPIC_API_KEY=your-anthropic-api-key
```

### Coordinate conventions

Models do not agree on how to express a point. Most answer in absolute image
pixels, but several — Qwen-VL, Gemini, and GLM-V among them — answer on a
0-1000 grid independent of the real image size. Because a normalized answer can
never exceed 1000 while the screenshots are 2205 pixels tall, scoring a
normalized model as `pixel` compresses every prediction into the top-left
corner. The result is 0% accuracy on every row, and McNemar reports
`Inconclusive (floor)` for every profile — a measurement artifact that is easily
mistaken for a weak model.

Set `COORD_SPACE` to `pixel` (default) or `norm1000` to match the model under
test. Declaring it explicitly rather than inferring it keeps the convention a
recorded property of each published run.

To determine a model's convention from an existing results file, or to repair a
run that was scored under the wrong one, use `rescore_coords.py`. Raw model
responses are stored verbatim in the CSV, so both operations are offline and
cost no API calls:

```bash
python rescore_coords.py --csv dataset/evaluation_results_MODEL.csv --check
python rescore_coords.py --csv dataset/evaluation_results_MODEL.csv --coord-space norm1000
```

Rewriting a CSV writes a `.csv.bak` alongside it first. Rerun
`mcnemar_analysis.py` afterwards to refresh the statistics.

`VLM_PACE_SECONDS` is an optional non-negative delay between successful model
calls. `VLM_MAX_RETRIES` controls retries for provider failures. Use the key
for the selected LiteLLM model: `openai/` models require `OPENAI_API_KEY`,
`gemini/` models accept `GEMINI_API_KEY` or `GOOGLE_API_KEY`, and `anthropic/`
models require `ANTHROPIC_API_KEY`.

## End-to-end workflow

### 1. Collect Android screenshots and labels

Run all built-in target screens and profiles:

```bash
python orchestrator.py
```

The configured screen list is `settings_main`, `contacts`, `dialer`,
`messages`, and `clock`. For every screen/profile pair, the orchestrator
applies the profile, navigates to the target screen, captures a PNG and XML,
checks that the XML belongs to the expected app, extracts JSON bounds, and
resets the emulator after that screen.

Validate the collection flow without ADB or an emulator:

```bash
python orchestrator.py --dry-run
```

Collect only selected screens:

```bash
python orchestrator.py --screens settings_main dialer
```

### 2. Run offline VLM evaluation

After collection, run:

```bash
python vlm_evaluator.py
```

The evaluator discovers screen names from `dataset/labels/*_baseline.json`,
uses baseline labels to select unambiguous text targets, evaluates every
configured profile, and logs hit-test results to:

```text
dataset/evaluation_results_{model}.csv
```

Here `{model}` is the `VLM_MODEL` value with `/` replaced by `_`; for example,
`openai/gpt-4o-mini` produces
`dataset/evaluation_results_openai_gpt-4o-mini.csv`.

The evaluator has no command-line flags. Set `VLM_MODEL` and optional pacing
or retry settings in `.env` (or the process environment) before running it.

### 3. Run McNemar analysis

Analyze every `evaluation_results_*.csv` file in `dataset/`:

```bash
python mcnemar_analysis.py
```

To analyze one results file:

```bash
python mcnemar_analysis.py --csv dataset/evaluation_results_openai_gpt-4o-mini.csv
```

For each input, the script compares each experimental profile with baseline,
uses asymptotic McNemar when there are at least 25 discordant pairs and an
exact binomial test otherwise, and writes:

```text
dataset/mcnemar_results_{model}.csv
```

## Standalone utilities

The collection helpers can also be run directly when an emulator is connected:

```bash
python layout_modifier.py elder_combo_max
python layout_modifier.py reset
python screenshot_pipeline.py my_capture
python bound_extractor.py outputs/my_capture.xml
```

The standalone screenshot pipeline writes to `outputs/` by default. In the
normal workflow, `orchestrator.py` instead routes captures to `dataset/`.

## Troubleshooting

### ADB or emulator is unavailable

Start an AVD, wait for Android to finish booting, and run `adb devices`. Ensure
the Platform Tools directory is on `PATH`. The collection and standalone
utilities require a connected device; `python orchestrator.py --dry-run` does
not.

### The evaluator reports no screens found

No baseline label files were found in `dataset/labels`. Run the collection
pipeline first, or ensure the directory contains files named
`{screen}_baseline.json` alongside the matching profile assets.

### The evaluator skips a model for a missing key

Add a non-placeholder provider key to `.env` or the process environment. Values
that still use the `your-...-here` placeholder are deliberately treated as
missing. Confirm the `VLM_MODEL` prefix and key match the provider.

### `VLM_MODEL` is not set

Set it in `.env` or export it before running the evaluator:

```bash
export VLM_MODEL=openai/gpt-4o-mini
python vlm_evaluator.py
```

### SciPy is not installed

Analysis continues with fallback calculations. Install SciPy when precise
p-values are required:

```bash
python -m pip install scipy
```
