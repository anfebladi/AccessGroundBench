# AccessGroundBench

AccessGroundBench is a small Android UI data-collection toolkit. It captures
synchronized screenshots and accessibility/layout XML from an Android emulator,
then converts the XML into JSON bounding-box records for later evaluation.

## What each script does

- `screenshot_pipeline.py` captures the active emulator screen as a `.png` and
  dumps the Android UI hierarchy as a matching `.xml` file.
- `layout_modifier.py` applies accessibility stress profiles to the emulator,
  including larger text, density changes, and RTL layout.
- `bound_extractor.py` converts one captured XML hierarchy into cleaned JSON
  bounding-box records.

Generated captures and extracted JSON are written to `outputs/`. Existing
files in `sample_input/` are committed sample/reference inputs.

## Prerequisites

This project currently expects a local Android emulator.

You need:

- Python 3
- Android Studio
- Android SDK Platform Tools, especially `adb`
- An Android virtual device from Android Studio Device Manager

Install Android Studio from:

https://developer.android.com/studio

## Set up ADB on macOS

First, check whether `adb` is already available:

```bash
adb devices
```

If you see `zsh: command not found: adb`, add Android SDK Platform Tools to
your shell path.

For the current terminal only:

```bash
export PATH="$HOME/Library/Android/sdk/platform-tools:$PATH"
```

To make it permanent:

```bash
echo 'export PATH="$HOME/Library/Android/sdk/platform-tools:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

Then verify again:

```bash
adb devices
```

## Start an emulator

1. Open Android Studio.
2. Go to `Tools > Device Manager`.
3. Create a virtual device if you do not already have one.
4. Start the virtual device.
5. Wait until Android fully boots to the home screen.
6. In this project directory, run:

```bash
adb devices
```

Expected output should include a device with status `device`:

```text
List of devices attached
emulator-5554    device
```

If `adb devices` only prints `List of devices attached` with no device rows,
the emulator is not running or has not finished booting yet.

## Run a basic capture

From the project root:

```bash
python3 screenshot_pipeline.py
```

This writes a timestamped `.xml` and `.png` pair into `outputs/`, for example:

```text
outputs/capture_20260703_185059.xml
outputs/capture_20260703_185059.png
```

You can also provide a custom output name:

```bash
python3 screenshot_pipeline.py my_capture_name
```

That writes:

```text
outputs/my_capture_name.xml
outputs/my_capture_name.png
```

## Apply layout stress profiles

Use `layout_modifier.py` to change the emulator display configuration before a
capture.

Choose one profile and pass it to `layout_modifier.py`:

```bash
python3 layout_modifier.py <profile_name>
```

Available stress profiles:

- `baseline`
- `elder_text_heavy`
- `elder_zoom_heavy`
- `elder_combo_max`
- `elder_combo_rtl`

`reset` is the restore command, not a stress profile:

```bash
python3 layout_modifier.py reset
```

Example selectable profile commands:

```bash
python3 layout_modifier.py elder_text_heavy
python3 layout_modifier.py elder_zoom_heavy
python3 layout_modifier.py elder_combo_max
python3 layout_modifier.py elder_combo_rtl
```

For example, `elder_combo_max` can be swapped for any other profile:

```bash
python3 layout_modifier.py elder_combo_max
python3 screenshot_pipeline.py
python3 layout_modifier.py reset
```

Always reset the emulator after stress-profile captures:

```bash
python3 layout_modifier.py reset
```

## Extract JSON bounds from XML

After you have a captured XML file, convert it to JSON:

```bash
python3 bound_extractor.py outputs/capture_20260703_185059.xml
```

The JSON file is written next to the XML with the same base name:

```text
outputs/capture_20260703_185059.json
```

To test the extractor with a committed sample input, run:

```bash
python3 bound_extractor.py sample_input/capture_20260702_191657.xml
```

That creates a local JSON file next to the sample XML:

```text
sample_input/capture_20260702_191657.json
```

## Troubleshooting

### `zsh: command not found: adb`

Your terminal cannot find Android SDK Platform Tools. Run:

```bash
export PATH="$HOME/Library/Android/sdk/platform-tools:$PATH"
```

For a permanent fix, add the same export to `~/.zshrc`:

```bash
echo 'export PATH="$HOME/Library/Android/sdk/platform-tools:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### `adb devices` shows no devices

If the output looks like this:

```text
List of devices attached
```

then no emulator is connected. Start an emulator from Android Studio
`Tools > Device Manager`, wait for Android to fully boot, and run:

```bash
adb devices
```

again.

### `No authorized device found`

The scripts could not find an emulator with status `device`. Confirm:

```bash
adb devices
```

You need at least one row like:

```text
emulator-5554    device
```

### `DeprecationWarning: datetime.datetime.utcnow()`

This warning can appear when running `screenshot_pipeline.py` on newer Python
versions. It is harmless for now; the capture script still runs.

## Typical full workflow

From the project root, run:

```bash
export PATH="$HOME/Library/Android/sdk/platform-tools:$PATH"
adb devices
python3 layout_modifier.py elder_combo_max
python3 screenshot_pipeline.py
python3 layout_modifier.py reset
python3 bound_extractor.py outputs/<captured_file_name>.xml
```

Replace `<captured_file_name>` with the actual XML file stem created in
`outputs/`.
