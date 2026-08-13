# Collection runbook

Use this checklist for a live Android capture. The [collection guide](../collection.md)
is the reference for workflow details, artifacts, validation, and recovery; the
[CLI reference](../cli-reference.md#agb-collect) documents command syntax.

## Before starting

- Use the authorized operator and the attached Pixel 6 AVD (Android 14, API 34,
  x86_64).
- Confirm the emulator is fully booted and listed as `device`:

  ```bash
  adb devices
  ```

- Sign in to Play. Open Messages, Gmail, and Maps once, clear first-run dialogs,
  and return to the home screen.
- Confirm the working tree and dataset destination are the intended ones.

## Collect

1. Preview the run. This makes no ADB calls, captures, or manifest writes, but
   may create required dataset directories:

   ```bash
   agb collect --dry-run
   ```

2. Run a one-screen smoke capture:

   ```bash
   agb collect --screens settings_main
   ```

3. If the smoke capture succeeds, run the full collection:

   ```bash
   agb collect
   ```

The configured run has 12 screens and six profiles: `baseline` plus five
experimental profiles (`elder_text_heavy`, `elder_zoom_heavy`, `elder_combo_max`,
`elder_combo_mid`, and `colorblind_deuteranomaly`). There is no RTL arm. Each
screen receives seven captures (the six profiles plus `baseline_close`), and the
device is reset to baseline after each screen.

## Validate and stop

Inspect `experiment/dataset/images/`, `experiment/dataset/raw_xml/`, `experiment/dataset/labels/`, and
`experiment/dataset/collection_manifest.json`. Stop the run and investigate if any command
returns nonzero or reports problems; do not proceed to evaluation with an
unresolved manifest problem. See the [collection guide](../collection.md) for
artifact and validation details.

## Recovery

- To recapture selected screens, rerun with `--screens`; the resulting manifest
  merges existing records for unrelated screens.
- If profile state is uncertain, restore the device baseline:

  ```bash
  agb profile reset
  ```

- To rebuild from existing assets without ADB or new captures, use offline
  manifest rebuild. A selected-screen rebuild merges those records with the
  existing unrelated records:

  ```bash
  agb collect --rebuild-manifest
  agb collect --rebuild-manifest --screens settings_main
  ```

See the [collection guide](../collection.md) and [CLI reference](../cli-reference.md#agb-collect)
for recovery semantics and command details.
