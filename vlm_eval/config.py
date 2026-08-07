"""Configuration and project paths for VLM evaluation."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = PROJECT_ROOT / "dataset"
IMAGES_DIR = DATASET_DIR / "images"
LABELS_DIR = DATASET_DIR / "labels"

MODEL_ENV_VAR: str = "VLM_MODEL"
PACE_ENV_VAR: str = "VLM_PACE_SECONDS"
A11Y_TREE_ENV_VAR: str = "USE_A11Y_TREE"
COORD_SPACE_ENV_VAR: str = "COORD_SPACE"

# Coordinate conventions a model may answer in. "pixel" means absolute image
# pixels; "norm1000" means a resolution-independent 0-1000 grid that must be
# rescaled by the image dimensions before hit-testing.
COORD_SPACES = ("pixel", "norm1000")
DEFAULT_COORD_SPACE = "pixel"

ALL_PROFILES = [
    "baseline",
    "elder_text_heavy",
    "elder_zoom_heavy",
    "elder_combo_max",
    "elder_combo_rtl",
    "colorblind_deuteranomaly",
]


def resolve_model(cli_model: str | None) -> str:
    """Resolve model precedence: CLI override, then VLM_MODEL env."""
    if cli_model:
        return cli_model

    env_model = os.environ.get(MODEL_ENV_VAR, "").strip()
    if env_model:
        return env_model

    print(f"[ERROR] {MODEL_ENV_VAR} is not set.")
    print("")
    print("  To fix this, set a LiteLLM model string in .env, for example:")
    print("  VLM_MODEL=openai/gpt-4o-mini")
    print("")
    print("  Or set it in the environment for a single run:")
    print("  VLM_MODEL=openai/gpt-4o-mini python vlm_evaluator.py")
    print("")
    print("  vlm_evaluator.py takes no command-line flags; it reads .env only.")
    raise SystemExit(1)


def resolve_use_a11y_tree() -> bool:
    """Resolve the accessibility tree toggle from USE_A11Y_TREE env var.

    Returns True when the env var is set to a truthy value (true/1/yes).
    Defaults to False when unset or empty.
    """
    raw = os.environ.get(A11Y_TREE_ENV_VAR, "").strip().lower()
    return raw in ("true", "1", "yes")


def resolve_coord_space() -> str:
    """Resolve the model's coordinate convention from COORD_SPACE.

    Models disagree on how to express a point. Most answer in absolute image
    pixels, but several (Qwen-VL, Gemini, GLM-V) answer on a 0-1000 grid
    regardless of the real image size. Scoring a normalized answer as pixels
    compresses every prediction into the top-left corner, which makes a hit
    arithmetically impossible and reports 0% accuracy for an otherwise capable
    model. This is declared per model rather than guessed so that a published
    result records which convention it was scored under.
    """
    raw = os.environ.get(COORD_SPACE_ENV_VAR, "").strip().lower()
    if not raw:
        return DEFAULT_COORD_SPACE

    if raw not in COORD_SPACES:
        print(f"[ERROR] {COORD_SPACE_ENV_VAR} must be one of {', '.join(COORD_SPACES)}; got: {raw}")
        raise SystemExit(1)

    return raw


def resolve_pace_seconds(cli_pace_seconds: str | None) -> float:
    """Resolve optional per-call pacing: CLI override, env, then 0 seconds."""
    raw_value = cli_pace_seconds
    source = "--pace-seconds"
    if raw_value is None:
        raw_value = os.environ.get(PACE_ENV_VAR, "").strip()
        source = PACE_ENV_VAR

    if raw_value in (None, ""):
        return 0.0

    try:
        pace_seconds = float(raw_value)
    except ValueError:
        print(f"[ERROR] {source} must be a number of seconds, got: {raw_value}")
        raise SystemExit(1)

    if pace_seconds < 0:
        print(f"[ERROR] {source} must be >= 0, got: {raw_value}")
        raise SystemExit(1)

    return pace_seconds


def get_results_csv(model: str, use_a11y_tree: bool = False) -> Path:
    """Generate a dynamic CSV path based on the model name.

    When use_a11y_tree is True, appends '_with_tree' to distinguish
    tree-injected results from vision-only results.
    """
    clean_model = model.replace("/", "_")
    suffix = "_with_tree" if use_a11y_tree else ""
    return DATASET_DIR / f"evaluation_results_{clean_model}{suffix}.csv"
