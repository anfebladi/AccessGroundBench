# Methods and reproducibility

[Back to README](../README.md)

This benchmark evaluates whether Android accessibility layout transformations impair a VLM's ability to ground UI text elements. Each experiment uses a paired design: the same model receives the same grounding queries under a baseline layout and under each experimental accessibility profile, then the hit-rate difference is evaluated with McNemar's test.

## Reference environment

- **Host:** Windows 11, Android Studio
- **Emulator:** Android 14 (API 34), Pixel 6 hardware profile, x86_64 system image, 1080 × 2400 px screen, 420 dpi
- **Python:** 3.11
- All target applications were pre-launched once to dismiss first-run dialogs.
- A Google Account was used to unlock apps requiring authentication.

## Target applications

The default experiment uses 13 Android screens: `settings_main`, `settings_display`, `settings_network`, `settings_accessibility`, `contacts`, `dialer`, `messages`, `clock`, `maps`, `play_store`, `gmail`, `youtube`, and `photos`.

Apps requiring unavailable hardware (Camera), apps not installed by default (Files), and apps that failed to reliably launch on the test emulator (Chrome) were excluded from the default run. The source registry retains these targets as opt-in entries, along with Calculator and Calendar, for explicit `--screens` runs.

## Accessibility profiles

Six profiles are applied programmatically before each screen capture:

| Profile | Font scale | Screen density | Force RTL | Color filter |
|---|---:|---|---|---|
| `baseline` | 1.0× | Device default | Off | None |
| `elder_text_heavy` | 1.4× | Default | Off | None |
| `elder_zoom_heavy` | 1.0× | 480 dpi | Off | None |
| `elder_combo_max` | 1.6× | 520 dpi | Off | None |
| `elder_combo_rtl` | 1.5× | 480 dpi | On | None |
| `colorblind_deuteranomaly` | 1.0× | Default | Off | Deuteranomaly (green-weak) |

Profiles use these ADB settings:

- Font scale: `adb shell settings put system font_scale <value>`
- Screen density: `adb shell wm density <value>` / `wm density reset`
- RTL layout: `adb shell settings put global development_settings_force_rtl <0|1>`
- Color filter: Android daltonizer secure settings

A 2.5-second stabilization delay follows each profile application. The deuteranomaly filter is applied in software to the saved PNG with a 3×3 RGB matrix because `adb screencap` captures display buffers before Android's hardware daltonizer transform is applied.

## Data collection

For each screen × profile pair:

1. Apply the profile and wait 2.5 seconds.
2. Launch the app with `adb shell am start`, confirm the foreground package, and auto-dismiss permission dialogs.
3. Run `adb shell uiautomator dump` with a 15-second timeout and retry up to three times on failure or timeout.
4. Capture the screenshot immediately after the XML dump.
5. Pull both files to the host.
6. Crop status and navigation bars using dimensions detected from `dumpsys window displays`.
7. Apply the software deuteranomaly matrix for the colorblind profile.
8. Parse XML and save interactive nodes with non-empty text and non-zero bounds as JSON.
9. Reset all four display vectors to baseline.

## Target harvesting

Targets are harvested from each `{screen}_baseline.json` file. The evaluator includes only non-empty, non-whitespace text whose value appears exactly once on that screen. The same target set is used for every profile of that screen.

## VLM evaluation

General-purpose models use this grounding prompt:

```text
You are an autonomous mobile agent operating an Android phone.
Look closely at this image and find the UI element with the text '{target_text}'.
Provide the exact central pixel (x,y) coordinates of that element.
```

The evaluator sends a provider-level strict JSON Schema requiring an object with one `coordinates` property containing exactly two numeric values. The provider unwraps that property into the evaluator's internal `[x, y]` format. Hosted requests use `temperature=0` and a 32-token output cap. Responses with prose, extra values, or another JSON shape are invalid; the evaluator does not fall back to prompt-only formatting.

Ferret-UI uses its fine-tuned prompt:

```text
Provide the bounding box of the text '{target_text}'.
```

Its server uses deterministic decoding by default and converts a valid bounding-box response to the evaluator's canonical `[x, y]` format.

A prediction is a hit when the predicted `(x, y)` falls within the target element's bounding box expanded by ±30 px on all sides. This simulates Google's 48 dp minimum touch-target guideline. Results are written to `evaluation_results_{model}.csv`.

## Statistical analysis

McNemar's paired test is calculated for each screen × profile:

| | Experimental pass | Experimental fail |
|---|---|---|
| **Baseline pass** | *a* | *b* (Broke it) |
| **Baseline fail** | *c* (Fluke recovery) | *d* |

- `n = b + c` is the number of discordant pairs.
- When `n ≥ 25`, use asymptotic χ² with continuity correction.
- When `n < 25`, use exact two-tailed binomial testing with H₀: `P(b) = 0.5`.
- Set `Floor_Limited = Yes` when baseline accuracy is below 50%.

