"""Screenshot cropping and deterministic color transformations."""

from pathlib import Path

# ---------------------------------------------------------------------------
# Software color-vision transforms (applied to the captured PNG).
#
# Android's on-device daltonizer is a display-pipeline color transform that
# `adb screencap` does NOT capture -- the saved PNG comes out with original
# colors. To make a colorblind profile actually affect the pixels the VLM
# sees, we apply the equivalent transform in software here. Deterministic and
# reproducible, independent of emulator/Android version.
#
# Matrices are the Machado et al. (2009) severity-1.0 color-vision-deficiency
# matrices (sRGB, row-major 3x3), plus a luma grayscale for monochromacy.
# ---------------------------------------------------------------------------
COLOR_TRANSFORMS: dict[str, tuple[float, ...]] = {
    "protanomaly": (
        0.152286, 1.052583, -0.204868,
        0.114503, 0.786281, 0.099216,
        -0.003882, -0.048116, 1.051998,
    ),
    "deuteranomaly": (
        0.367322, 0.860646, -0.227968,
        0.280085, 0.672501, 0.047413,
        -0.011820, 0.042940, 0.968881,
    ),
    "tritanomaly": (
        1.255528, -0.076749, -0.178779,
        -0.078411, 0.930809, 0.147602,
        0.004733, 0.691367, 0.303900,
    ),
    "monochromacy": (
        0.299, 0.587, 0.114,
        0.299, 0.587, 0.114,
        0.299, 0.587, 0.114,
    ),
}

def crop_screenshot(
    png_path: Path,
    top_crop: int,
    bottom_crop: int,
) -> None:
    """
    Phase 3.5 — Crop the status bar and navigation/gesture bar from a
    screenshot in-place using Pillow.

    Args:
        png_path:    Path to the PNG file to crop.
        top_crop:    Number of pixels to remove from the top (status bar).
        bottom_crop: Number of pixels to remove from the bottom (nav bar).
    """
    from PIL import Image

    if top_crop == 0 and bottom_crop == 0:
        print("  [3.5] No crop needed (bar heights = 0).")
        return

    print(f"  [3.5] Cropping screenshot: top={top_crop}px, bottom={bottom_crop}px")

    with Image.open(png_path) as img:
        width, height = img.size
        crop_box = (0, top_crop, width, height - bottom_crop)
        cropped = img.crop(crop_box)
        cropped.save(png_path)

    print(f"  [OK]  Cropped {png_path.name}: {width}x{height} -> {width}x{height - top_crop - bottom_crop}")


def apply_color_transform(png_path: Path, color_mode: str) -> float:
    """Remap a screenshot's colors in-place to emulate a color-vision deficiency.

    Uses the matrices in COLOR_TRANSFORMS. This is what makes a colorblind
    profile visible in the saved pixels, since `adb screencap` does not
    capture Android's on-device daltonizer.

    Args:
        png_path:   Path to the PNG file to transform.
        color_mode: Key into COLOR_TRANSFORMS (e.g. "deuteranomaly").

    Returns the mean absolute per-channel change, and raises RuntimeError if
    the transform left the pixels untouched.
    """
    from PIL import Image, ImageChops, ImageStat

    matrix = COLOR_TRANSFORMS.get(color_mode)
    if matrix is None:
        valid = ", ".join(COLOR_TRANSFORMS)
        raise RuntimeError(
            f"Unknown color_mode '{color_mode}' (valid: {valid}). Refusing to "
            f"save an untransformed image under a colorblind profile."
        )

    print(f"  [3.6] Applying color transform: {color_mode}")

    # PIL's convert() takes a 12-tuple (3x4) for an RGB->RGB affine map;
    # append a zero offset to each row. Out-of-range results are clamped.
    tuple_12 = (
        matrix[0], matrix[1], matrix[2], 0.0,
        matrix[3], matrix[4], matrix[5], 0.0,
        matrix[6], matrix[7], matrix[8], 0.0,
    )
    with Image.open(png_path) as img:
        original = img.convert("RGB")
        transformed = original.convert("RGB", tuple_12)
        # Comparing before-and-after on the same bytes, rather than diffing
        # against a separate baseline capture, keeps this exact: app content
        # drift between two captures cannot mask a transform that silently
        # did nothing.
        stat = ImageStat.Stat(ImageChops.difference(original, transformed))
        delta = sum(stat.mean) / len(stat.mean)
        transformed.save(png_path)

    # The magnitude scales with how colourful the screen is -- a green-weak
    # transform barely moves a dark, near-monochrome UI -- so only "changed
    # at all" is a meaningful pass condition, not any particular delta.
    if delta == 0.0:
        raise RuntimeError(
            f"Color transform '{color_mode}' changed nothing in "
            f"{png_path.name}; the colorblind profile would be identical to "
            f"baseline."
        )

    print(f"  [OK]  Color transform applied to {png_path.name} "
          f"(mean channel delta {delta:.2f})")
    return delta
