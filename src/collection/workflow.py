"""
workflow.py
---------------
Master data-collection driver for AccessGroundBench.

For each target screen:
  1. Capture an opening baseline
  2. For each experimental profile: apply -> verify -> navigate -> capture ->
     validate -> extract labels
  3. Capture a closing baseline
  4. Reset the emulator

Two things about that order matter.

**Baseline bracketing.** The opening and closing baselines are captured minutes
apart around the same screen, so diffing them measures how much the app changed
its own content during the sweep. That per-screen *drift rate* is the empirical
noise floor: an effect smaller than the drift cannot be told apart from a
rotating carousel or a ticking clock. An earlier run captured baselines days
away from their comparison profiles and never measured this, leaving a 6.3%
drift silently mixed into every result.

**Verification.** Each profile is read back from the device, and colour filtering is
additionally checked against the captured PNG (before/after diff inside the colour
transform). An earlier run wrote an RTL settings key Android does not read; even after
that was fixed and empirically checked against captures, RTL still measured 0% mirrored
on every screen, so the arm was dropped -- see `elder_combo_mid` in `profiles`.

Assets are written to:
  dataset/images/{screen}_{profile}.png
  dataset/raw_xml/{screen}_{profile}.xml
  dataset/labels/{screen}_{profile}.json
  dataset/collection_manifest.json

The command-line adapter is ``collection.cli.collect_main``.
"""

import json
import sys

from .artifacts import labels, manifest
from .pipeline import capture
from .runtime import navigation, profiles
from .screens import SCREENS

from paths import (
    DATASET_DIR,
    IMAGES_DIR,
    LABELS_DIR,
    MANIFEST_PATH,
    PROJECT_ROOT,
    RAW_XML_DIR,
)

# The closing baseline, captured after a screen's profiles, used only to measure
# drift. It is not an experimental condition.
DRIFT_PROBE = manifest.DRIFT_PROBE

# Screens whose drift exceeds this share of their baseline texts are flagged:
# their effects are not separable from the app changing its own content.
DRIFT_WARN_RATIO = manifest.DRIFT_WARN_RATIO

def ensure_dirs() -> None:
    """Create the dataset directory structure if it doesn't exist."""
    for d in (IMAGES_DIR, RAW_XML_DIR, LABELS_DIR):
        d.mkdir(parents=True, exist_ok=True)
        print(f"  [DIR] {d}")


def capture_one(screen_name: str, profile_name: str, stem: str) -> dict:
    """
    Navigate to a screen and capture its assets under the current profile.

    Returns a manifest entry describing what happened. Failures are recorded
    rather than raised so one bad screen does not abandon the run -- but they
    are recorded, which is what makes the final manifest able to fail the run.
    """
    entry = {"screen": screen_name, "profile": profile_name, "stem": stem, "ok": False}

    print(f"\n  [NAV] Navigating to {screen_name}...")
    try:
        navigation.navigate_to_screen(screen_name)
    except SystemExit:
        entry["error"] = "navigation failed"
        print(f"  [ERROR] Navigation failed for {stem}")
        return entry

    color_mode = profiles.ELDER_PROFILES.get(
        profile_name, profiles.ELDER_PROFILES["baseline"]
    ).get("daltonizer", "off")

    print(f"  [CAP] Capturing {stem}...")
    try:
        xml_path, png_path, status_bar_h, nav_bar_h = capture.run_pipeline(
            output_name=stem,
            image_dir=IMAGES_DIR,
            xml_dir=RAW_XML_DIR,
            color_mode=color_mode,
        )
        navigation.validate_xml_package(xml_path, screen_name)

        label_path = LABELS_DIR / f"{stem}.json"
        labels.run(
            str(xml_path),
            output_path=str(label_path),
            y_offset=status_bar_h,
            bottom_crop=nav_bar_h,
        )
        with open(label_path, encoding="utf-8") as f:
            label_count = len(json.load(f))
    except RuntimeError as e:
        entry["error"] = str(e)
        print(f"  [ERROR] Capture failed for {stem}: {e}")
        return entry

    entry.update({
        "ok": True,
        "png": str(png_path),
        "xml": str(xml_path),
        "labels": str(label_path),
        "label_count": label_count,
    })
    print(f"  [DONE] {stem}")
    return entry


def run_screen(screen_name: str, dry_run: bool = False) -> tuple[list[dict], dict | None]:
    """
    Capture every profile for one screen, bracketed by two baselines.

    Returns (capture entries, drift record).
    """
    navigation.get_screen_target(screen_name)

    experimental = [p for p in profiles.ELDER_PROFILES if p != "baseline"]
    # baseline first, profiles, then baseline again as a drift probe.
    sequence = ["baseline", *experimental, DRIFT_PROBE]

    if dry_run:
        for profile_name in sequence:
            stem = f"{screen_name}_{profile_name}"
            applied = "baseline" if profile_name == DRIFT_PROBE else profile_name
            print(f"  [DRY-RUN] {stem:<50} (applies profile '{applied}')")
        print(f"  [DRY-RUN] Would diff baseline vs {DRIFT_PROBE} for drift")
        return [], None

    entries = []
    for profile_name in sequence:
        stem = f"{screen_name}_{profile_name}"
        applied_profile = "baseline" if profile_name == DRIFT_PROBE else profile_name

        print(f"\n{'-' * 60}")
        print(f"  Screen: {screen_name}  |  Profile: {profile_name}")
        print(f"{'-' * 60}")

        try:
            profiles.apply_profile(applied_profile)
        except profiles.ProfileVerificationError as exc:
            print(f"  [ABORT] Profile '{applied_profile}' did not apply: {exc}")
            entries.append({
                "screen": screen_name, "profile": profile_name, "stem": stem,
                "ok": False, "error": f"profile verification failed: {exc}",
            })
            continue

        entry = capture_one(screen_name, applied_profile, stem)
        entries.append(entry)

    print(f"\n  [RESET] Reverting emulator to baseline for screen: {screen_name}")
    profiles.reset_all()

    return entries, manifest.measure_drift(screen_name, entries)


def run_collection(
    screens: list[str],
    *,
    dry_run: bool = False,
    rebuild_manifest: bool = False,
) -> None:
    """Run collection or rebuild its manifest for an explicit screen order."""
    if rebuild_manifest:
        print("=" * 60)
        print("  AccessGroundBench -- Orchestrator")
        print("  Mode    : REBUILD-MANIFEST (offline, no emulator, no new captures)")
        print(f"  Screens : {', '.join(screens)}")
        print("=" * 60)

        ensure_dirs()

        all_entries: list[dict] = []
        all_drifts: list[dict] = []
        for screen_name in screens:
            entries, drift = manifest.rebuild_screen(screen_name)
            all_entries.extend(entries)
            if drift is not None:
                all_drifts.append(drift)

        problems = manifest.write_manifest(screens, all_entries, all_drifts, reconstructed=True)

        print("\n" + "=" * 60)
        print("  Manifest rebuild complete")
        print(f"  Reconstructed : {sum(1 for e in all_entries if e['ok'])} of "
              f"{len(screens) * manifest.PER_SCREEN_EXPECTED} captures for this run's screens")
        print(f"  Manifest      : {MANIFEST_PATH}")
        if problems:
            print(f"\n  {len(problems)} PROBLEM(S) across the full manifest:")
            for problem in problems:
                print(f"    - {problem}")
            print("=" * 60)
            sys.exit(1)
        print("  No problems found.")
        print("=" * 60)
        return

    print("=" * 60)
    print("  AccessGroundBench -- Orchestrator")
    print(f"  Mode    : {'DRY-RUN' if dry_run else 'LIVE'}")
    print(f"  Screens : {', '.join(screens)}")
    print(f"  Profiles: {', '.join(profiles.ELDER_PROFILES)}")
    print(f"  Probe   : {DRIFT_PROBE} (closing baseline, drift measurement only)")
    print("=" * 60)

    ensure_dirs()

    all_entries: list[dict] = []
    all_drifts: list[dict] = []
    for screen_name in screens:
        entries, drift = run_screen(screen_name, dry_run=dry_run)
        all_entries.extend(entries)
        if drift is not None:
            all_drifts.append(drift)

    if dry_run:
        per_screen = len(profiles.ELDER_PROFILES) + 1
        print("\n" + "=" * 60)
        print(f"  Dry run complete. Would capture "
              f"{len(screens) * per_screen} assets "
              f"({len(screens)} screens x {per_screen} captures).")
        print("=" * 60)
        return

    problems = manifest.write_manifest(screens, all_entries, all_drifts)

    print("\n" + "=" * 60)
    print("  Collection complete")
    print(f"  Captures : {sum(1 for e in all_entries if e['ok'])} of "
          f"{len(screens) * (len(profiles.ELDER_PROFILES) + 1)}")
    print(f"  Manifest : {MANIFEST_PATH}")

    if problems:
        print(f"\n  {len(problems)} PROBLEM(S) -- this dataset is not ready to use:")
        for problem in problems:
            print(f"    - {problem}")
        print("=" * 60)
        sys.exit(1)

    print("  No problems found.")
    print("=" * 60)
