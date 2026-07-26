# Setup

[Back to README](../README.md)

## Requirements

| Requirement | Version |
|---|---|
| Python | 3.11 or later |
| uv | Latest stable release |
| Node.js / npm *(optional)* | Required for the 9Router gateway |
| Android Studio / AVD | Any recent release |
| Android SDK Platform Tools (`adb`) | Any recent release |
| CUDA-capable GPU *(optional)* | Required only for local Ferret-UI |

The main project's Python dependencies are declared in `pyproject.toml`:

```text
litellm >= 1.91.3
Pillow >= 10.0
python-dotenv >= 1.0
scipy  (optional — for precise McNemar p-values)
```

Install with `uv` (recommended) or `pip`:

```bash
uv sync
# or: pip install .

# optional: precise McNemar p-values
pip install scipy
```

## Configure environment variables

Copy the template:

```bash
cp .env.example .env
```

At minimum, set `VLM_MODEL` and the API key required by its provider. A typical `.env` contains:

```dotenv
# Comma-separated list of models to evaluate (evaluated in sequence)
VLM_MODEL=openai/gpt-4o-mini, gemini/gemini-2.5-pro, local/ferret-ui-llama8b

VLM_PACE_SECONDS=0
VLM_MAX_RETRIES=3
VLM_REQUEST_TIMEOUT_SECONDS=120
USE_A11Y_TREE=false

GEMINI_API_KEY=your-gemini-api-key-here
GOOGLE_API_KEY=your-google-api-key-here
OPENAI_API_KEY=your-openai-api-key-here
ANTHROPIC_API_KEY=your-anthropic-api-key-here

# Optional: local 9Router using Codex/other subscription quota
NINEROUTER_BASE_URL=http://localhost:20128/v1
NINEROUTER_API_KEY=your-9router-api-key-here
```

Model prefix → required key:

| Model prefix | Key variable |
|---|---|
| `openai/` | `OPENAI_API_KEY` |
| `gemini/` | `GEMINI_API_KEY` or `GOOGLE_API_KEY` |
| `anthropic/` | `ANTHROPIC_API_KEY` |
| `local/ferret-ui-llama8b` | Ferret-UI server; see [`integrations.md`](integrations.md) |
| `9router/` | `NINEROUTER_BASE_URL` + `NINEROUTER_API_KEY` |

LiteLLM normalizes the request format, but provider credentials remain provider-specific for direct native routes. Native providers can be mixed in the comma-separated `VLM_MODEL` list. Compatibility requests time out after 120 seconds by default and retry transient timeout, connection, and rate-limit failures according to `VLM_MAX_RETRIES`.

Set `USE_A11Y_TREE=true` to include the captured accessibility tree alongside the screenshot during evaluation. Tree-injected results receive a `_with_tree` suffix, for example `outputs/evaluation_results/evaluation_results_openai_gpt-4o-mini_with_tree.csv`.

## Set up the Android emulator

1. Open **Android Studio → Device Manager → Create Virtual Device**.
2. Select the **Pixel 6** hardware profile.
3. Select **Android 14 (API 34), x86_64**.
4. Start the AVD and wait for it to fully boot.
5. Verify ADB sees it:

   ```bash
   adb devices
   # Expected output:
   # List of devices attached
   # emulator-5554   device
   ```

On Windows, if `adb` is not on PATH, use the full path such as `C:\Users\<you>\AppData\Local\Android\Sdk\platform-tools\adb.exe`.

## Prepare the emulator

Some apps require one-time manual setup before the orchestrator can navigate to them automatically:

1. Open the Play Store and sign in with a Google Account. This unlocks Gmail, YouTube, Maps, and Photos.
2. Open Messages, Gmail, and Google Maps once and dismiss their welcome screens or permission dialogs.
3. Return the emulator to the home screen before running the orchestrator.

The optional 9Router gateway and local Ferret-UI model are documented in [`integrations.md`](integrations.md).

