# AccessGroundBench

AccessGroundBench is a research benchmark that measures how Android accessibility layout changes—large fonts, zoomed displays, RTL layouts, and color filters—affect a vision-language model's (VLM's) ability to locate UI text elements on screen.

The pipeline has three stages:

1. **Collect** screenshots and UI hierarchy XML from an Android emulator under a baseline layout and five accessibility-stress profiles.
2. **Evaluate** VLM grounding predictions against ground-truth bounding boxes.
3. **Analyze** baseline-versus-experimental accuracy with McNemar's paired statistical test.

## Requirements

| Requirement | Version |
|---|---|
| Python | 3.11 or later |
| uv | Latest stable release |
| Node.js / npm *(optional)* | Required for the 9Router gateway |
| Android Studio / AVD | Any recent release |
| Android SDK Platform Tools (`adb`) | Any recent release |
| CUDA-capable GPU *(optional)* | Required only for local Ferret-UI |

Install the main project with `uv` (recommended) or `pip`:

```bash
uv sync
# or: pip install .
```

For the complete dependency list, environment variables, and emulator setup, see [`docs/setup.md`](docs/setup.md).

## Quick start

1. Clone the repository and enter it:

   ```bash
   git clone <repo-url>
   cd AccessGroundBench
   ```

2. Configure the VLM provider:

   ```bash
   cp .env.example .env
   ```

   Set `VLM_MODEL` and the matching provider key in `.env`. The provider mapping and optional gateway setup are documented in [`docs/setup.md`](docs/setup.md) and [`docs/integrations.md`](docs/integrations.md).

3. Start and prepare an Android 14 (API 34) Pixel 6 emulator. Confirm that it is visible to ADB:

   ```bash
   adb devices
   ```

4. Collect the benchmark data:

   ```bash
   uv run python -m collection.orchestrator
   ```

5. Run VLM evaluation:

   ```bash
   uv run python -m vlm_eval.cli
   ```

6. Run paired statistical analysis:

   ```bash
   uv run python -m mcnemar.cli
   ```

For dry runs, selecting individual screens, output details, and standalone utilities, see [`docs/workflow.md`](docs/workflow.md).

## Project layout

```text
AccessGroundBench/
├── src/
│   ├── collection/           # Android/ADB collection pipeline
│   ├── vlm_eval/             # VLM evaluation pipeline
│   └── mcnemar/              # Paired statistical analysis
├── ferret_ui/                # Optional local Ferret-UI inference server
├── dataset/                  # Collected data and committed reference results
├── outputs/                  # Active evaluation and McNemar CSV results
├── tests/                    # Unit and smoke tests
├── .env.example              # Environment variable template
└── pyproject.toml            # Project metadata and dependencies
```

Python imports and commands use the packages `collection`, `vlm_eval`, and `mcnemar`:

```bash
uv run python -m collection.orchestrator
uv run python -m vlm_eval.cli
uv run python -m mcnemar.cli
```

The default collection run uses 13 enabled screens: `settings_main`, `settings_display`, `settings_network`, `settings_accessibility`, `contacts`, `dialer`, `messages`, `clock`, `maps`, `play_store`, `gmail`, `youtube`, and `photos`. The navigation registry also contains `calculator`, `calendar`, `chrome`, `camera`, and `files`, which can be requested explicitly with `--screens` when supported by the emulator.

## Documentation

| Guide | Contents |
|---|---|
| [`docs/setup.md`](docs/setup.md) | Dependencies, `.env`, provider keys, Android emulator setup |
| [`docs/workflow.md`](docs/workflow.md) | Collection, evaluation, analysis, outputs, and utilities |
| [`docs/integrations.md`](docs/integrations.md) | 9Router and local Ferret-UI |
| [`docs/troubleshooting.md`](docs/troubleshooting.md) | Common emulator, pipeline, provider, and test failures |
| [`docs/methods.md`](docs/methods.md) | Experimental design and reproducibility details |

## Accessibility profiles

The benchmark applies six profiles before each capture: `baseline`, `elder_text_heavy`, `elder_zoom_heavy`, `elder_combo_max`, `elder_combo_rtl`, and `colorblind_deuteranomaly`. Their exact display settings and implementation are described in [`docs/methods.md`](docs/methods.md).

## Tests

After installing the project, run the existing unit and smoke tests with:

```bash
uv run python -m unittest discover -s tests
```

