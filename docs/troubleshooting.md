# Troubleshooting

[Back to README](../README.md)

## `adb devices` shows no device

- Make sure the AVD is fully booted and the home screen is visible.
- On Windows, confirm the Platform Tools path is correct or add it to PATH.
- If the emulator disconnected after a script crash, run:

  ```bash
  adb kill-server && adb start-server
  ```

## The orchestrator freezes without output

`uiautomator dump` can hang when a system popup covers the screen. The script times out after 15 seconds and skips the frozen capture automatically. If it consistently freezes on one screen, manually dismiss system dialogs on the emulator.

## `ERROR: null root node returned by UiTestAutomationBridge`

The app had not finished rendering when `uiautomator dump` was called. The orchestrator retries automatically. If the error persists, try increasing `SETTLE_DELAY` in `src/collection/device/layout_modifier.py`.

## The evaluator reports no screens found

No baseline label files exist in `dataset/labels/`. Run:

```bash
uv run python -m collection.orchestrator
```

## A model key is missing

Set the correct key in `.env`. Values that still contain `your-...-here` are treated as unset. Check that the `VLM_MODEL` prefix matches the provider key variable in [`setup.md`](setup.md).

For 9Router, confirm that the local router is running, `NINEROUTER_BASE_URL` points to its OpenAI-compatible `/v1` endpoint, and `NINEROUTER_API_KEY` matches the dashboard key. Copy the route exactly from the dashboard after the `9router/` prefix.

If the dashboard does not load, restart the `9router` process and confirm that port `20128` is available.

## `VLM_MODEL` is not set

Set it temporarily for one run:

```bash
VLM_MODEL=openai/gpt-4o-mini uv run python -m vlm_eval.cli
```

## McNemar results show `Floor_Limited=Yes`

This means baseline accuracy is below 50%, so the model is failing to ground most elements even under the unmodified layout. Possible causes include:

- Prompt format mismatch, especially for Ferret-UI.
- A model without vision capability.
- Bounding boxes that are too small relative to prediction precision; consider increasing `TOLERANCE` in `src/vlm_eval/scoring.py`.

## Run the tests

After installing the project:

```bash
uv run python -m unittest discover -s tests
```

