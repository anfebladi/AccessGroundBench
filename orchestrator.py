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
from collections import defaultdict
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


# Every screen has the same profile sweep: baseline, the experimental
# profiles, then the closing drift probe.
def _expected_stems(screen_name: str) -> set[str]:
    experimental = [p for p in layout_modifier.ELDER_PROFILES if p != "baseline"]
    return {
        f"{screen_name}_{profile}"
        for profile in ["baseline", *experimental, DRIFT_PROBE]
    }


PER_SCREEN_EXPECTED = len(layout_modifier.ELDER_PROFILES) + 1  # +1 for DRIFT_PROBE


def load_existing_manifest() -> dict:
    """
    Load the on-disk manifest's per-screen records, or an empty map.

    Tolerates the pre-merge flat schema (screens: list[str], captures:
    list[dict], drift: list[dict]) by treating it as if nothing were on
    disk -- there is nothing per-screen to carry forward from that shape,
    and any screen it covered will simply be rebuilt fresh the next time
    this repo's collection or --rebuild-manifest touches it.
    """
    if not MANIFEST_PATH.is_file():
        return {}
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    screens = manifest.get("screens")
    return screens if isinstance(screens, dict) else {}


def _entries_by_stem(captures: list[dict]) -> dict[str, dict]:
    """
    Index successful captures by stem, not by 'profile'.

    capture_one/rebuild_capture_entry both stamp the drift probe's entry with
    profile="baseline" (it applies the baseline profile) even though its stem
    is "{screen}_baseline_close" -- so two entries can share profile=="baseline"
    for one screen, and keying a dict by "profile" would let one silently
    overwrite the other. Stem is unique per capture and is what callers here
    actually need: a specific file to load off disk.
    """
    return {e["stem"]: e for e in captures if e["ok"]}


def contamination_problems(screen_name: str, captures: list[dict]) -> list[str]:
    """
    B0 hard gate: every geometry-preserving profile's captured text set must
    equal baseline's exactly (see capture_checks.colour_only_contamination and
    layout_modifier.is_geometry_preserving). A colour-only profile cannot move
    or remove a layout element, so any difference is instrument contamination,
    not ordinary reachability loss -- unlike a geometry-changing profile, where
    losing some tail of texts to scroll-off is expected and not a problem.

    Returns [] when the baseline capture itself failed, or its label file is
    not on disk; that gap is already reported by the missing-capture check,
    and there is nothing to compare against here.
    """
    by_stem = _entries_by_stem(captures)
    baseline_entry = by_stem.get(f"{screen_name}_baseline")
    if baseline_entry is None or not Path(baseline_entry["labels"]).is_file():
        return []

    baseline_labels = capture_checks.load_labels(baseline_entry["labels"])
    problems = []

    for profile_name in layout_modifier.ELDER_PROFILES:
        if profile_name == "baseline":
            continue
        if not layout_modifier.is_geometry_preserving(profile_name):
            continue
        entry = by_stem.get(f"{screen_name}_{profile_name}")
        if entry is None or not Path(entry["labels"]).is_file():
            continue

        profile_labels = capture_checks.load_labels(entry["labels"])
        vanished, appeared = capture_checks.colour_only_contamination(
            baseline_labels, profile_labels
        )
        if vanished or appeared:
            problems.append(
                f"colour-only contamination: {screen_name}/{profile_name} changed "
                f"{len(vanished)} vanished / {len(appeared)} appeared text(s) despite "
                f"no geometry vector differing from baseline "
                f"(vanished={sorted(vanished)}, appeared={sorted(appeared)})"
            )

    return problems


def shape_diagnostics(screen_name: str, captures: list[dict]) -> list[str]:
    """
    Soft, non-fatal companion to contamination_problems: for each
    geometry-CHANGING profile, note when its losses relative to baseline are
    scattered rather than a contiguous tail (see capture_checks.loss_shape).
    Never appears in `problems` and never fails a run -- recorded in the
    manifest under `diagnostics` for a human to look at, because the shape
    heuristic has a known false-positive source (container nodes whose box
    spans their children).
    """
    by_stem = _entries_by_stem(captures)
    baseline_entry = by_stem.get(f"{screen_name}_baseline")
    if baseline_entry is None or not Path(baseline_entry["labels"]).is_file():
        return []

    baseline_labels = capture_checks.load_labels(baseline_entry["labels"])
    notes = []

    for profile_name in layout_modifier.ELDER_PROFILES:
        if profile_name == "baseline" or layout_modifier.is_geometry_preserving(profile_name):
            continue
        entry = by_stem.get(f"{screen_name}_{profile_name}")
        if entry is None or not Path(entry["labels"]).is_file():
            continue

        profile_labels = capture_checks.load_labels(entry["labels"])
        shape = capture_checks.loss_shape(baseline_labels, profile_labels)
        if shape is not None and not shape["is_tail"]:
            notes.append(
                f"{screen_name}/{profile_name}: {shape['lost_count']} of "
                f"{shape['baseline_count']} texts lost, scattered rather than a "
                f"contiguous tail -- may be content change, may be a container "
                f"node whose box spans its children (see capture_checks.loss_shape)"
            )

    return notes


def screen_problems(screen_name: str, captures: list[dict], drift: dict | None) -> list[str]:
    """Problems scoped to one screen: missing captures, empty extraction, high
    drift, and colour-only contamination.

    Called from write_manifest, which both run_screen (live collection) and
    rebuild_screen (--rebuild-manifest, offline) feed into -- so this is the
    single point where the B0 contamination gate applies to both paths; there
    is no separate call site to keep in sync.
    """
    captured_stems = {e["stem"] for e in captures if e["ok"]}

    problems = [
        f"missing capture: {stem}"
        for stem in sorted(_expected_stems(screen_name) - captured_stems)
    ]
    problems += [
        f"empty extraction: {e['stem']} (uiautomator dump returned no usable nodes "
        f"despite a successful capture -- see settings_main_baseline in the archive "
        f"for the known failure mode)"
        for e in captures
        if e["ok"] and e.get("label_count") == 0
    ]
    if drift is not None and drift["flagged"]:
        problems.append(f"high content drift: {screen_name} at {drift['drift_rate']:.1%}")
    problems += contamination_problems(screen_name, captures)
    return problems


def write_manifest(
    screens: list[str],
    entries: list[dict],
    drifts: list[dict],
    reconstructed: bool = False,
) -> list[str]:
    """Merge this run's captures into the on-disk manifest, by screen.

    Returns every problem found across the full merged manifest -- not just
    the screens this call touched.
    """
    # Two failure modes motivate merging rather than overwriting:
    #
    # (1) A previous run lost one capture to a caught-and-ignored exception,
    # which shrank a profile from 168 to 165 targets with nothing in the
    # output to say so -- the manifest exists so a gap cannot be silent.
    #
    # (2) write_manifest used to overwrite the file unconditionally. A
    # `--screens settings_main` run -- a normal way to spot-check one screen
    # before a full collection -- silently replaced a full 13-screen
    # manifest with a 1-screen one, erasing the completeness and drift
    # record for the other 12 screens even though their captures were
    # untouched on disk. Merging by screen means a subset run can only ever
    # update the screens it actually captured; every other screen's record
    # is carried forward unchanged.
    existing_screens = load_existing_manifest()

    stale = sorted(set(existing_screens) - set(screens))
    if stale:
        print(f"\n  [WARN] This run covers {len(screens)} screen(s); the manifest "
              f"already on disk also covers {len(stale)} screen(s) this run did "
              f"not touch: {', '.join(stale)}. Those entries are being carried "
              f"forward unchanged from when they were last captured. If you "
              f"intended a full re-collection, this manifest is a splice of "
              f"more than one run -- check each screen's own collected_at.")

    entries_by_screen: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        entries_by_screen[e["screen"]].append(e)
    drift_by_screen = {d["screen"]: d for d in drifts}

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for screen_name in screens:
        captures = entries_by_screen.get(screen_name, [])
        drift = drift_by_screen.get(screen_name)
        diagnostics = shape_diagnostics(screen_name, captures)
        if diagnostics:
            print(f"\n  [DIAGNOSTIC] {screen_name}:")
            for note in diagnostics:
                print(f"    - {note}")
        existing_screens[screen_name] = {
            "collected_at": now,
            "reconstructed": reconstructed,
            "captures": captures,
            "drift": drift,
            "problems": screen_problems(screen_name, captures, drift),
            "diagnostics": diagnostics,
        }

    all_problems = [
        p for record in existing_screens.values() for p in record["problems"]
    ]
    total_expected = PER_SCREEN_EXPECTED * len(existing_screens)
    total_successful = sum(
        sum(1 for e in record["captures"] if e["ok"])
        for record in existing_screens.values()
    )

    manifest = {
        "generated_at": now,
        "profiles": list(layout_modifier.ELDER_PROFILES),
        "drift_probe": DRIFT_PROBE,
        "expected_captures": total_expected,
        "successful_captures": total_successful,
        "screens": existing_screens,
        "problems": all_problems,
    }

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"\n  [MANIFEST] {len(existing_screens)} screen(s) on record, "
          f"{total_successful} of {total_expected} captures, "
          f"{len(all_problems)} problem(s) total.")

    return all_problems


def rebuild_capture_entry(screen_name: str, profile_name: str, stem: str) -> dict:
    """
    Reconstruct one capture's manifest entry from files already on disk,
    with no ADB calls and no emulator -- the counterpart to capture_one for
    --rebuild-manifest.
    """
    entry = {"screen": screen_name, "profile": profile_name, "stem": stem, "ok": False}

    png_path = IMAGES_DIR / f"{stem}.png"
    xml_path = RAW_XML_DIR / f"{stem}.xml"
    label_path = LABELS_DIR / f"{stem}.json"
    if not (png_path.is_file() and xml_path.is_file() and label_path.is_file()):
        entry["error"] = "missing capture files on disk"
        return entry

    with open(label_path, encoding="utf-8") as f:
        label_count = len(json.load(f))

    entry.update({
        "ok": True,
        "png": str(png_path),
        "xml": str(xml_path),
        "labels": str(label_path),
        "label_count": label_count,
    })
    return entry


def rebuild_screen(screen_name: str) -> tuple[list[dict], dict | None]:
    """Reconstruct one screen's entries and drift record from disk only."""
    experimental = [p for p in layout_modifier.ELDER_PROFILES if p != "baseline"]
    sequence = ["baseline", *experimental, DRIFT_PROBE]
    entries = [
        rebuild_capture_entry(screen_name, profile_name, f"{screen_name}_{profile_name}")
        for profile_name in sequence
    ]
    return entries, measure_drift(screen_name, entries)


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
    parser.add_argument(
        "--rebuild-manifest",
        action="store_true",
        help="Reconstruct the manifest for --screens (default: all) from "
             "images/raw_xml/labels already on disk. No emulator, no ADB, no "
             "new captures -- use this to recover the manifest after a "
             "subset run overwrote it, or to get a provenance record for a "
             "dataset collected before this flag existed.",
    )
    args = parser.parse_args()

    screens = args.screens or SCREENS
    dry_run = args.dry_run

    if args.rebuild_manifest:
        print("=" * 60)
        print("  AccessGroundBench -- Orchestrator")
        print("  Mode    : REBUILD-MANIFEST (offline, no emulator, no new captures)")
        print(f"  Screens : {', '.join(screens)}")
        print("=" * 60)

        ensure_dirs()

        all_entries: list[dict] = []
        all_drifts: list[dict] = []
        for screen_name in screens:
            entries, drift = rebuild_screen(screen_name)
            all_entries.extend(entries)
            if drift is not None:
                all_drifts.append(drift)

        problems = write_manifest(screens, all_entries, all_drifts, reconstructed=True)

        print("\n" + "=" * 60)
        print("  Manifest rebuild complete")
        print(f"  Reconstructed : {sum(1 for e in all_entries if e['ok'])} of "
              f"{len(screens) * PER_SCREEN_EXPECTED} captures for this run's screens")
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
