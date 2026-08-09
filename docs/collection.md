# Android collection guide

This guide covers the reproducible live-capture workflow behind
`dataset/collection_manifest.json`. Install the project and prepare the
emulator as described in [`setup.md`](setup.md) before starting. For command
syntax, see the [`agb collect` reference](cli-reference.md#agb-collect).

## Prerequisites

- Android Studio/AVD with a Pixel 6 running Android 14 (API 34), x86_64.
- A fully booted emulator that appears as `device` in `adb devices`.
- A Google Account signed in to Play Store.
- Open Messages, Gmail, and Google Maps once to clear first-run dialogs, then
  return to the home screen.

The built-in collection has 13 screens, in this order:

```text
settings_main settings_display settings_network settings_accessibility
contacts dialer messages clock maps play_store gmail youtube photos
```

Six profiles are collected: `baseline`, `elder_text_heavy`,
`elder_zoom_heavy`, `elder_combo_max`, `elder_combo_mid`, and
`colorblind_deuteranomaly`. There is no current RTL arm; RTL is retained only
in the archived experiment.

## Workflow

For each screen, collection captures an opening `baseline`, then each of the
five non-baseline profiles, and finally `baseline_close`, a closing baseline
used only as a drift probe. The emulator is reset to baseline after each
screen. A full run therefore expects seven captures per screen (six profiles
plus the closing probe).

For every capture the runner applies the profile, waits for Android to settle,
reads back and verifies the settings, navigates to the target screen, captures
the UI, and validates that the expected package is in the hierarchy. It then
extracts labels and validates the resulting artifacts. Do not manually change
display settings between profiles: the read-back check is part of the
measurement.

Preview the sequence without an emulator, ADB calls, captures, or manifest
writes. The command may still create the required dataset directories:

```bash
agb collect --dry-run
```

To collect a subset, pass screen names explicitly:

```bash
agb collect --screens settings_main contacts dialer
```

## Artifacts and validation

Each successful capture writes one image, raw UI hierarchy, and extracted-label
file:

```text
dataset/images/{screen}_{profile}.png
dataset/raw_xml/{screen}_{profile}.xml
dataset/labels/{screen}_{profile}.json
```

The pipeline dumps XML with retries (up to three attempts, waiting up to
15 seconds for a usable hierarchy), captures the screenshot immediately, then
crops status/navigation bars. The colorblind profile also receives the
software deuteranomaly transform in the saved image; Android's on-device
daltonizer is not relied on for pixels.

`dataset/collection_manifest.json` records captures, label counts, drift, and
problems. A run fails validation for missing captures, empty labels, content
drift above 5%, or color-only contamination (a geometry-preserving profile
whose text set differs from baseline). Scattered geometric loss is recorded as
a diagnostic, not a hard failure, because it can indicate content change or a
container node whose bounds span its children.

## Recovery

If captures exist but the manifest is missing or stale, reconstruct it offline:

```bash
agb collect --rebuild-manifest
agb collect --rebuild-manifest --screens settings_main
```

Rebuild reads existing images, XML, and labels; it makes no ADB calls and does
not capture new assets. With `--screens`, selected screen records are rebuilt,
while other existing screen records are preserved in the merged manifest.
Inspect any reported `problems` before evaluation. For device, navigation, or
provider failures, see [`troubleshooting.md`](troubleshooting.md); measurement
assumptions and estimands are in [`METHODS.md`](../METHODS.md).
