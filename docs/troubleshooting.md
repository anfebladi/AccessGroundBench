# Troubleshooting

## `adb devices` shows no device

Make sure the AVD is fully booted. On Windows, add Android SDK Platform Tools
to `PATH` or use its full path. After a disconnect, restart ADB:

```bash
adb kill-server
adb start-server
```

## Collection hangs or UI XML fails

`uiautomator dump` can hang when a system popup covers the screen; dismiss the
popup and retry. A `null root node returned by UiTestAutomationBridge` usually
means the app has not finished rendering; the workflow retries automatically.

## Evaluator reports no screens

No baseline labels exist under `dataset/labels/`. Run `agb collect` first.

## A provider key is missing

Set the key required by the `VLM_MODEL` prefix in `.env`. Placeholder values
such as `your-...-here` are treated as unset. For `9router/`, confirm the local
router is running and `NINEROUTER_BASE_URL` points to its OpenAI-compatible
`/v1` endpoint. For `openai_compatible/`, set both the base URL and API key.

## `VLM_MODEL` is not set

Set it for a single run:

```bash
VLM_MODEL=openai/gpt-4o-mini agb evaluate
```

## Evaluation resumes unexpectedly or is locked

Evaluation resumes completed rows by default. Use `agb evaluate --fresh` to
discard rows and restart, or `agb evaluate --force-unlock` to remove a stale
lock left by a killed process. See the [CLI reference](cli-reference.md#agb-evaluate).

## Analysis reports `floor` or `ceiling`

These power flags mean the comparison is underpowered: baseline accuracy is
below 50% (`floor`) or above 95% (`ceiling`). They are not evidence of model
resilience. Check the prompt/provider configuration and inspect target boxes if
the baseline is unexpectedly low.

## Ferret-UI does not respond

Run the server in its separate `ferret_ui` environment, confirm it is listening
on port 8000, and wait for `Model loaded successfully!`. Ferret inference can
take a long time; its default request timeout is 1,800 seconds. See
[`ferret-ui.md`](ferret-ui.md).
