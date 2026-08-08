"""
rescore_coords.py
-----------------
Re-score an existing evaluation CSV under a different coordinate convention.

Model responses are stored verbatim in the raw_response column, so a run that
was scored under the wrong convention can be repaired offline with no further
API calls. Use --check to inspect a file's likely convention before committing
to a rewrite.
"""

import argparse
import csv
import shutil
import sys
from pathlib import Path

from vlm_eval.config import COORD_SPACES, DATASET_DIR, IMAGES_DIR
from vlm_eval.results import CSV_COLUMNS
from vlm_eval.runner import get_png_dimensions
from vlm_eval.scoring import hit_test, parse_coordinates, to_pixel_space


def _dimensions_for(screen: str, profile: str) -> tuple[int, int] | None:
    """Look up a capture's pixel dimensions, or None when the PNG is missing."""
    image_path = IMAGES_DIR / f"{screen}_{profile}.png"
    if not image_path.is_file():
        return None
    try:
        return get_png_dimensions(image_path)
    except Exception:
        return None


def _baseline_boxes(rows: list[dict]) -> dict[tuple[str, str], list[int]]:
    """Map (screen, target_text) to its baseline box for constant strictness."""
    boxes = {}
    for row in rows:
        if row.get("profile") != "baseline":
            continue
        try:
            box = [int(float(row[k])) for k in ("x_min", "y_min", "x_max", "y_max")]
        except (ValueError, KeyError):
            continue
        boxes[(row["screen"], row["target_text"])] = box
    return boxes


def rescore(rows: list[dict], coord_space: str) -> tuple[list[dict], int, int]:
    """Re-score every row under coord_space. Returns (rows, scored, hits)."""
    baselines = _baseline_boxes(rows)
    scored = hits = 0

    for row in rows:
        dims = _dimensions_for(row.get("screen", ""), row.get("profile", ""))
        try:
            box = [int(float(row[k])) for k in ("x_min", "y_min", "x_max", "y_max")]
        except (ValueError, KeyError):
            box = None

        if dims is None or box is None:
            # Off-screen rows and missing captures keep their recorded outcome.
            continue

        img_width, img_height = dims
        x_raw, y_raw = parse_coordinates(row.get("raw_response", ""))
        x_coord, y_coord = to_pixel_space(
            x_raw, y_raw, img_width, img_height, coord_space
        )

        if (
            x_coord < 0
            or y_coord < 0
            or x_coord > img_width
            or y_coord > img_height
        ):
            x_pred, y_pred, score = -1, -1, 0
        else:
            x_pred, y_pred = int(x_coord), int(y_coord)
            score = hit_test(
                x_pred,
                y_pred,
                box,
                baselines.get((row["screen"], row["target_text"])),
            )

        row["x_pred"], row["y_pred"], row["score"] = x_pred, y_pred, score
        scored += 1
        hits += score

    return rows, scored, hits


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-score an evaluation CSV under a different coordinate convention"
    )
    parser.add_argument("--csv", type=Path, required=True, help="evaluation_results_*.csv to rescore")
    parser.add_argument(
        "--coord-space",
        choices=COORD_SPACES,
        help="Convention to score under. Required unless --check is used.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report accuracy under every convention without writing anything",
    )
    args = parser.parse_args()

    if not args.csv.is_file():
        print(f"[ERROR] CSV not found: {args.csv}")
        raise SystemExit(1)
    if not args.check and not args.coord_space:
        print("[ERROR] --coord-space is required unless --check is passed.")
        raise SystemExit(1)

    with open(args.csv, newline="", encoding="utf-8") as f:
        original = list(csv.DictReader(f))

    if not original:
        print(f"[ERROR] No rows in {args.csv}")
        raise SystemExit(1)

    if args.check:
        print(f"  {args.csv.name}")
        print(f"  {'convention':<12} {'scored':>7} {'hits':>6} {'accuracy':>9}")
        print(f"  {'-' * 12} {'-' * 7} {'-' * 6} {'-' * 9}")
        for space in COORD_SPACES:
            rows = [dict(r) for r in original]
            _, scored, hits = rescore(rows, space)
            acc = f"{hits / scored * 100:.1f}%" if scored else "n/a"
            print(f"  {space:<12} {scored:>7} {hits:>6} {acc:>9}")
        print("\n  The convention with materially higher accuracy is the one the")
        print("  model answers in. Rerun with --coord-space to apply it.")
        return

    rows, scored, hits = rescore(original, args.coord_space)

    backup = args.csv.with_suffix(".csv.bak")
    shutil.copy2(args.csv, backup)

    with open(args.csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_COLUMNS)
        for row in rows:
            writer.writerow([row.get(col, "") for col in CSV_COLUMNS])

    acc = f"{hits / scored * 100:.1f}%" if scored else "n/a"
    print(f"  Rescored {args.csv.name} as {args.coord_space}")
    print(f"  Backup:   {backup.name}")
    print(f"  Scored:   {scored} rows, {hits} hits ({acc})")
    print(f"\n  Now rerun: python mcnemar_analysis.py --csv {args.csv}")


if __name__ == "__main__":
    main()
