"""
orchestrator.py
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
on every screen, so the arm was dropped -- see `elder_combo_mid` in `layout_modifier.py`.

Assets are written to:
  dataset/images/{screen}_{profile}.png
  dataset/raw_xml/{screen}_{profile}.xml
  dataset/labels/{screen}_{profile}.json
  dataset/collection_manifest.json

Usage:
  python orchestrator.py                  # full run (requires emulator)
  python orchestrator.py --dry-run        # validate logic without an emulator
  python orchestrator.py --screens clock  # subset
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent
DATASET_DIR = PROJECT_ROOT / "dataset"
IMAGES_DIR = DATASET_DIR / "images"
RAW_XML_DIR = DATASET_DIR / "raw_xml"
LABELS_DIR = DATASET_DIR / "labels"
MANIFEST_PATH = DATASET_DIR / "collection_manifest.json"

# ---------------------------------------------------------------------------
# Target screen list -- add screens here as needed
SCREENS: list[str] = [
    "settings_main", "settings_display", "settings_network", "settings_accessibility",
    "contacts", "dialer", "messages",
    "clock",
    "maps", "play_store",
    "gmail", "youtube", "photos",
]

# The closing baseline, captured after a screen's profiles, used only to measure
# drift. It is not an experimental condition.
DRIFT_PROBE = "baseline_close"

# Screens whose drift exceeds this share of their baseline texts are flagged:
# their effects are not separable from the app changing its own content.
DRIFT_WARN_RATIO = 0.05

# ---------------------------------------------------------------------------
# Imports from sibling scripts (used as libraries)
# ---------------------------------------------------------------------------
import app_navigator
import bound_extractor
import capture_checks
import layout_modifier
import screenshot_pipeline


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
        app_navigator.navigate_to_screen(screen_name)
    except SystemExit:
        entry["error"] = "navigation failed"
        print(f"  [ERROR] Navigation failed for {stem}")
        return entry

    color_mode = layout_modifier.ELDER_PROFILES.get(
        profile_name, layout_modifier.ELDER_PROFILES["baseline"]
    ).get("daltonizer", "off")

    print(f"  [CAP] Capturing {stem}...")
    try:
        xml_path, png_path, status_bar_h, nav_bar_h = screenshot_pipeline.run_pipeline(
            output_name=stem,
            image_dir=IMAGES_DIR,
            xml_dir=RAW_XML_DIR,
            color_mode=color_mode,
        )
        app_navigator.validate_xml_package(xml_path, screen_name)

        label_path = LABELS_DIR / f"{stem}.json"
        bound_extractor.run(
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


def measure_drift(screen_name: str, entries: list[dict]) -> dict | None:
    """Diff the opening and closing baselines to get this screen's noise floor."""
    open_path = LABELS_DIR / f"{screen_name}_baseline.json"
    close_path = LABELS_DIR / f"{screen_name}_{DRIFT_PROBE}.json"
    if not (open_path.is_file() and close_path.is_file()):
        return None

    opening = capture_checks.load_labels(open_path)
    closing = capture_checks.load_labels(close_path)
    vanished, appeared = capture_checks.text_drift(opening, closing)
    rate = capture_checks.drift_rate(opening, closing)

    flagged = rate > DRIFT_WARN_RATIO
    marker = "WARN" if flagged else "OK"
    print(f"\n  [{marker}] Drift for {screen_name}: {rate:.1%} "
          f"({len(vanished)} vanished, {len(appeared)} appeared)")
    if flagged:
        print("         Effects smaller than this are not separable from the app "
              "changing its own content.")

    return {
        "screen": screen_name,
        "drift_rate": rate,
        "vanished": sorted(vanished),
        "appeared": sorted(appeared),
        "flagged": flagged,
    }


def run_screen(screen_name: str, dry_run: bool = False) -> tuple[list[dict], dict | None]:
    """
    Capture every profile for one screen, bracketed by two baselines.

    Returns (capture entries, drift record).
    """
    app_navigator.get_screen_target(screen_name)

    experimental = [p for p in layout_modifier.ELDER_PROFILES if p != "baseline"]
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
            layout_modifier.apply_profile(applied_profile)
        except layout_modifier.ProfileVerificationError as exc:
            print(f"  [ABORT] Profile '{applied_profile}' did not apply: {exc}")
            entries.append({
                "screen": screen_name, "profile": profile_name, "stem": stem,
                "ok": False, "error": f"profile verification failed: {exc}",
            })
            continue

        entry = capture_one(screen_name, applied_profile, stem)
        entries.append(entry)

    print(f"\n  [RESET] Reverting emulator to baseline for screen: {screen_name}")
    layout_modifier.reset_all()

    return entries, measure_drift(screen_name, entries)


def write_manifest(
    screens: list[str],
    entries: list[dict],
    drifts: list[dict],
) -> list[str]:
    """
    Record what was collected and return the list of problems found.

    A previous run lost one capture to a caught-and-ignored exception, which
    shrank a profile from 168 to 165 targets with nothing in the output to say
    so. The manifest exists so a gap cannot be silent.
    """
    experimental = [p for p in layout_modifier.ELDER_PROFILES if p != "baseline"]
    expected = [
        f"{screen}_{profile}"
        for screen in screens
        for profile in ["baseline", *experimental, DRIFT_PROBE]
    ]
    captured = {e["stem"] for e in entries if e["ok"]}

    problems = [f"missing capture: {stem}" for stem in expected if stem not in captured]
    problems += [
        f"empty extraction: {e['stem']} (uiautomator dump returned no usable nodes "
        f"despite a successful capture -- see settings_main_baseline in the archive "
        f"for the known failure mode)"
        for e in entries
        if e["ok"] and e.get("label_count") == 0
    ]
    problems += [
        f"high content drift: {d['screen']} at {d['drift_rate']:.1%}"
        for d in drifts
        if d["flagged"]
    ]

    manifest = {
        "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "screens": screens,
        "profiles": list(layout_modifier.ELDER_PROFILES),
        "drift_probe": DRIFT_PROBE,
        "expected_captures": len(expected),
        "successful_captures": len(captured),
        "captures": entries,
        "drift": drifts,
        "problems": problems,
    }

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    return problems


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AccessGroundBench -- Master Data Collection Orchestrator"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate pipeline logic without an emulator (no ADB calls)",
    )
    parser.add_argument(
        "--screens",
        nargs="+",
        default=None,
        help="Override the default screen list (e.g., --screens settings_main dialer)",
    )
    args = parser.parse_args()

    screens = args.screens or SCREENS
    dry_run = args.dry_run

    print("=" * 60)
    print("  AccessGroundBench -- Orchestrator")
    print(f"  Mode    : {'DRY-RUN' if dry_run else 'LIVE'}")
    print(f"  Screens : {', '.join(screens)}")
    print(f"  Profiles: {', '.join(layout_modifier.ELDER_PROFILES)}")
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
        per_screen = len(layout_modifier.ELDER_PROFILES) + 1
        print("\n" + "=" * 60)
        print(f"  Dry run complete. Would capture "
              f"{len(screens) * per_screen} assets "
              f"({len(screens)} screens x {per_screen} captures).")
        print("=" * 60)
        return

    problems = write_manifest(screens, all_entries, all_drifts)

    print("\n" + "=" * 60)
    print("  Collection complete")
    print(f"  Captures : {sum(1 for e in all_entries if e['ok'])} of "
          f"{len(screens) * (len(layout_modifier.ELDER_PROFILES) + 1)}")
    print(f"  Manifest : {MANIFEST_PATH}")

    if problems:
        print(f"\n  {len(problems)} PROBLEM(S) -- this dataset is not ready to use:")
        for problem in problems:
            print(f"    - {problem}")
        print("=" * 60)
        sys.exit(1)

    print("  No problems found.")
    print("=" * 60)


if __name__ == "__main__":
    main()
