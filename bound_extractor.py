"""
bound_extractor.py
------------------
Structural parsing layer that converts raw Android UI hierarchy XML files
into deterministic, machine-readable JSON datasets for AI evaluation.

Pipeline:
  [Raw .xml] -> DOM Traversal -> Regex Bounds Parse -> Filter & Normalize -> [Cleaned .json]
"""

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


# Regex pattern to extract four integer coordinates from "[x1,y1][x2,y2]"
BOUNDS_PATTERN = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def parse_bounds(bounds_str: str) -> tuple[int, int, int, int] | None:
    """
    Phase 2 — Extract pixel bounding box coordinates from the Android
    bounds attribute string format "[x1,y1][x2,y2]".

    Returns (x1, y1, x2, y2) as integers, or None if the string
    does not match the expected pattern.
    """
    match = BOUNDS_PATTERN.match(bounds_str)
    if not match:
        return None
    return tuple(int(v) for v in match.groups())


def trim_class_name(full_class: str) -> str:
    """
    Phase 3 — Truncate verbose Android Java package names to the
    short component type.

    Example: "android.widget.Button" -> "Button"
    """
    if not full_class:
        return ""
    return full_class.rsplit(".", 1)[-1]


def trim_resource_id(full_id: str) -> str:
    """
    Phase 3 — Strip the package prefix from resource IDs to keep
    only the unique element tag.

    Example: "com.android.launcher3:id/icon_shape" -> "icon_shape"
    """
    if not full_id:
        return ""
    if ":id/" in full_id:
        return full_id.split(":id/", 1)[-1]
    return full_id


def is_valid_node(bounds: tuple[int, int, int, int], screen_w: int, screen_h: int) -> bool:
    """
    Phase 3 — Reject invisible layout containers and full-screen wrappers.

    Filters out:
      - Zero-area nodes (e.g. [0,0][0,0])
      - Nodes whose bounds exactly span the full screen dimensions
    """
    x1, y1, x2, y2 = bounds
    width = x2 - x1
    height = y2 - y1

    # Reject zero-area nodes
    if width <= 0 or height <= 0:
        return False

    # Reject full-screen layout containers
    if x1 == 0 and y1 == 0 and x2 == screen_w and y2 == screen_h:
        return False

    return True


def extract(
    xml_path: str | Path,
    y_offset: int = 0,
    bottom_crop: int = 0,
) -> list[dict]:
    """
    Execute the full extraction pipeline on a single XML layout file.

    Phase 1: Parse the XML DOM and iterate all <node> elements.
    Phase 2: Extract and convert bounds strings to integer tuples.
    Phase 3: Filter invisible containers and normalize identifiers.
    Phase 3.5: Apply y_offset to shift bounds into cropped-image space
               and discard elements outside the visible content area.

    Args:
        y_offset:    Pixels to subtract from all Y coordinates (status bar height).
        bottom_crop: Pixels removed from the bottom (nav bar height).

    Returns a list of cleaned node dictionaries.
    """
    xml_path = Path(xml_path)
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Determine screen dimensions from the root-level hierarchy node
    # (first child is typically the full-screen FrameLayout)
    all_nodes = list(root.iter("node"))
    screen_w, screen_h = 1080, 2424  # fallback defaults

    if all_nodes:
        root_bounds = parse_bounds(all_nodes[0].get("bounds", ""))
        if root_bounds:
            screen_w = root_bounds[2]
            screen_h = root_bounds[3]

    # The visible content area after cropping
    content_top = y_offset
    content_bottom = screen_h - bottom_crop

    results = []

    for node in all_nodes:
        bounds_str = node.get("bounds", "")
        bounds = parse_bounds(bounds_str)

        if bounds is None:
            continue

        if not is_valid_node(bounds, screen_w, screen_h):
            continue

        x1, y1, x2, y2 = bounds

        # Skip elements entirely outside the cropped content area
        if y2 <= content_top or y1 >= content_bottom:
            continue

        # Clamp to the visible content area rather than keeping a node's
        # full, uncropped extent. A node that only partially overlaps the
        # crop (e.g. a list row clipped at the bottom edge) was previously
        # retained at full size, so its box's center could fall outside the
        # final image entirely -- hit_test would then score against a point
        # that is not on the screenshot. Clamping first, then shifting into
        # cropped-image space, guarantees every retained box lies within it.
        x1 = max(x1, 0)
        x2 = min(x2, screen_w)
        y1 = max(y1, content_top)
        y2 = min(y2, content_bottom)

        if x2 <= x1 or y2 <= y1:
            continue

        # Shift Y coordinates into the cropped image's coordinate space
        adjusted_bounds = (x1, y1 - y_offset, x2, y2 - y_offset)

        # Extract raw attributes
        raw_class = node.get("class", "")
        raw_text = node.get("text", "")
        raw_id = node.get("resource-id", "")
        content_desc = node.get("content-desc", "")

        record = {
            "class": trim_class_name(raw_class),
            "text": raw_text if raw_text else None,
            "content_desc": content_desc if content_desc else None,
            "resource_id": trim_resource_id(raw_id) if raw_id else None,
            "box": list(adjusted_bounds),
        }

        results.append(record)

    return results


def save_json(records: list[dict], output_path: str | Path) -> None:
    """
    Phase 4 — Serialize the filtered dataset to a UTF-8 encoded JSON file.
    """
    output_path = Path(output_path)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
    print(f"[SAVED] {len(records)} nodes -> {output_path}")


def run(
    xml_path: str,
    output_path: str | Path | None = None,
    y_offset: int = 0,
    bottom_crop: int = 0,
) -> Path:
    """
    Entry point: extract bounds from an XML file and save a matching JSON.

    Args:
        xml_path:    Path to the source XML layout hierarchy.
        output_path: Optional explicit path for the output JSON file.
                     Defaults to the same directory/stem as the XML input.
        y_offset:    Pixels to subtract from Y coordinates (status bar height).
        bottom_crop: Pixels removed from the bottom (nav bar height).

    Returns:
        The Path of the saved JSON file.
    """
    xml_path = Path(xml_path)

    if not xml_path.is_file():
        print(f"[ERROR] File not found: {xml_path}")
        sys.exit(1)

    print(f"[INPUT] {xml_path}")

    # Extract and filter
    records = extract(xml_path, y_offset=y_offset, bottom_crop=bottom_crop)
    print(f"[EXTRACTED] {len(records)} interactive nodes from layout tree")

    # Determine output path
    if output_path is not None:
        json_path = Path(output_path)
        json_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        json_path = xml_path.with_suffix(".json")

    save_json(records, json_path)
    return json_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python bound_extractor.py <path_to_xml>")
        sys.exit(1)
    run(sys.argv[1])
