# Setup

## Install the project

AccessGroundBench requires Python 3.11 or later. From the repository root:

```bash
uv sync
./scripts/install-agb.sh
cp .env.example .env
```

On macOS and Linux, the installer creates an `agb` symlink in
`${XDG_BIN_HOME:-$HOME/.local/bin}` that points to this clone's project
launcher. The launcher resolves the repository before invoking its environment,
so bare `agb ...` works from any directory inside the cloned repository. The
installer is idempotent for its own launcher, refuses to replace an unrelated
file unless `--force` is supplied, and does not edit shell configuration. If
the destination is not already on `PATH`, follow the PATH guidance printed by
the installer. On Windows, or without installing the launcher, run commands as
`uv run agb ...` instead.

`pip install .` is also supported, but `uv sync` is the recommended setup and
keeps the project launcher tied to the checkout.

## Configure providers

Set `VLM_MODEL` in `.env` to a comma-separated list of models. Hosted providers
use these variables:

| Model prefix | Required variable |
|---|---|
| `openai/` | `OPENAI_API_KEY` |
| `gemini/` | `GEMINI_API_KEY` or `GOOGLE_API_KEY` |
| `anthropic/` | `ANTHROPIC_API_KEY` |
| `9router/` | `NINEROUTER_BASE_URL` and `NINEROUTER_API_KEY` |
| `local/ferret-ui-llama8b` | running Ferret-UI server (see [ferret-ui.md](ferret-ui.md)) |

Optional provider controls include `VLM_PACE_SECONDS`, `VLM_MAX_RETRIES`,
`VLM_REQUEST_TIMEOUT_SECONDS` (default `120` seconds), `VLM_TEMPERATURE`,
`VLM_TRIALS`, and `VLM_TRIALS_MODELS`. `USE_A11Y_TREE=true` selects the
tree-injected prompt arm; unset or false selects vision-only mode.

## Prepare Android

Install Android Studio, create a Pixel 6 AVD using Android 14 (API 34),
x86_64, start it, and confirm:

```bash
adb devices
```

The device must be fully booted and listed as `device`. Sign in to a Google
Account in Play Store, open Messages, Gmail, and Google Maps once to dismiss
first-run dialogs, then return to the home screen before `agb collect`.

The complete per-screen sequence, profile matrix, artifact checks, and manifest
recovery procedure are in the [Android collection guide](collection.md).

## Coordinate conventions

Predictions are scored in cropped-image pixel coordinates. Gemini, Qwen, and GLM
families normally answer on a 0–1000 grid; their replies are detected and
converted automatically. `COORD_SPACE` defaults to `pixel` and can be set to
`norm1000` for an otherwise unregistered model. Do not override the convention
for a model that already self-describes its coordinates or for Ferret-UI.

To inspect or repair an existing CSV without API calls:

```bash
agb rescore --csv experiment/outputs/evaluations/MODEL_vision.csv --check
agb rescore --csv experiment/outputs/evaluations/MODEL_vision.csv --coord-space norm1000
```

Re-scoring writes a `.csv.bak`; run `agb analyze` again afterward. See the
[complete rescore options](cli-reference.md#agb-rescore).
