"""Model-neutral vision and accessibility-tree prompt construction."""

from .scoring import hit_test

PROMPT_TEMPLATE = (
    "You are an autonomous mobile agent navigating an Android user interface. "
    "Look closely at this image. This image is {img_width} x {img_height} pixels. "
    "Provide the exact central pixel (x, y) coordinates "
    "needed to click on the text element: '{target_text}'. "
    "Return your response strictly in the bracket format: [x, y]"
)

PROMPT_TEMPLATE_WITH_TREE = (
    "You are an autonomous mobile agent navigating an Android user interface. "
    "Look closely at this image. This image is {img_width} x {img_height} pixels. "
    "You are also given a partial accessibility tree listing some on-screen "
    "elements with their pixel bounds in the format [x1,y1][x2,y2]:\n"
    "{tree_text}\n"
    "The target element may not appear in this tree; use the surrounding "
    "elements' positions as spatial reference and the image to locate it. "
    "Provide the exact central pixel (x, y) coordinates "
    "needed to click on the text element: '{target_text}'. "
    "Return your response strictly in the bracket format: [x, y]"
)


def collect_tree_rows(
    profile_labels: list[dict],
    exclude_text: str | None = None,
    target_box: list[int] | None = None,
    baseline_box: list[int] | None = None,
) -> list[tuple[str, list[int]]]:
    """Collect a profile's label records into (label, box) rows.

    Each row is one UI element with its best available label and pixel
    bounding box, falling back through text -> content_desc -> resource_id
    -> class. This is the single source of truth for the tree exclusions
    below; every rendering of the tree (per-model prompt formats included)
    must be built from this function's output rather than re-deriving the
    fallback/exclusion logic, so a fix to one cannot silently regress while
    holding in another.
    """
    # Two independent exclusions keep the tree from handing the model the
    # answer. Both only ever REMOVE rows, so neither can inflate a
    # tree-mode result: a withheld row can make the task harder, never
    # easier.
    check_bounds = target_box is not None and baseline_box is not None

    rows = []
    for rec in profile_labels:
        box = rec.get("box")
        if not box:
            continue
        text = rec.get("text")
        label = (
            text
            or rec.get("content_desc")
            or rec.get("resource_id")
            or rec.get("class")
            or "?"
        )
        # LABEL exclusion: any element whose RENDERED LABEL matches the
        # target is withheld, so the tree never names the thing being asked
        # about. Checked against the same fallback chain used to build
        # `label` above, not against `text` alone -- a node with empty
        # `text` but `content_desc == exclude_text` still renders the
        # target's name, and checking `text` alone let 22 of 168 targets
        # (13.1%) leak through on the archived dataset.
        if (
            exclude_text is not None
            and label.strip() == exclude_text.strip()
        ):
            continue
        # BOUNDS exclusion: any row whose box centre would score a hit
        # under scoring.hit_test is withheld regardless of its label. The
        # label exclusion alone does not cover this -- a parent container
        # labelled e.g. "navigation_bar_item_content_container" never
        # renders the target's name, but its centre can sit inside the
        # target's scoring box, letting a model score by reading the tree
        # rather than looking at the image. Without it, the label
        # exclusion alone left 575 of 853 target x profile pairs (67.4%)
        # with at least one such hitting row, costing only ~3% of spatial
        # context to remove. Both boxes are required here since hit_test
        # scores a baseline-sized box centred on the current profile's box
        # (see scoring.hit_test); when either is None only the label
        # exclusion applies, keeping non-tree callers working unchanged.
        if check_bounds:
            centre_x = (box[0] + box[2]) // 2
            centre_y = (box[1] + box[3]) // 2
            if hit_test(centre_x, centre_y, target_box, baseline_box):
                continue
        rows.append((label, list(box)))
    return rows


def scale_tree_rows(
    rows: list[tuple[str, list[int]]], scale: float
) -> list[tuple[str, list[int]]]:
    """Rescale tree-row boxes into the coordinate space of a downscaled screenshot.

    A capped model (see providers.config.MAX_IMAGE_EDGE) is sent a screenshot
    smaller than the label boxes were measured in. Without this, its prompt
    would state tree bounds in one coordinate system while describing an
    image in another. scale is the same uniform factor
    providers.image_send_scale applied to the screenshot, so multiplying
    every coordinate by it keeps the tree and the image in agreement.

    Returns `rows` unchanged (same object) when scale >= 1.0 -- the common
    case, since only capped models scale below 1.0 -- so an uncapped model's
    prompt stays byte-identical to the pre-cap pipeline rather than being
    rebuilt through a no-op multiply/round.

    Rounding is per-coordinate, then clamped so x2 >= x1 and y2 >= y1: a
    1-2px source box can otherwise round to an inverted box. Sub-pixel
    rounding error is harmless here -- the tree is spatial context, not a
    scored coordinate, and collect_tree_rows already withholds any row
    whose centre would score a hit.
    """
    if scale >= 1.0:
        return rows
    scaled = []
    for label, (x1, y1, x2, y2) in rows:
        sx1, sy1 = round(x1 * scale), round(y1 * scale)
        sx2, sy2 = round(x2 * scale), round(y2 * scale)
        if sx2 < sx1:
            sx2 = sx1
        if sy2 < sy1:
            sy2 = sy1
        scaled.append((label, [sx1, sy1, sx2, sy2]))
    return scaled


def build_tree_text(
    profile_labels: list[dict],
    exclude_text: str | None = None,
    target_box: list[int] | None = None,
    baseline_box: list[int] | None = None,
) -> str:
    """Render a profile's label records into a compact accessibility-tree string.

    See collect_tree_rows for the fallback/exclusion rules this builds on.
    """
    lines = [
        f'- "{label}" [{x1},{y1}][{x2},{y2}]'
        for label, (x1, y1, x2, y2) in collect_tree_rows(
            profile_labels, exclude_text, target_box, baseline_box
        )
    ]
    return "\n".join(lines)

__all__ = [
    "PROMPT_TEMPLATE",
    "PROMPT_TEMPLATE_WITH_TREE",
    "build_tree_text",
    "collect_tree_rows",
    "scale_tree_rows",
]
