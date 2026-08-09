"""Configuration and project paths for VLM evaluation."""

import os
from pathlib import Path

from paths import DATASET_DIR

IMAGES_DIR = DATASET_DIR / "images"
LABELS_DIR = DATASET_DIR / "labels"

MODEL_ENV_VAR: str = "VLM_MODEL"
PACE_ENV_VAR: str = "VLM_PACE_SECONDS"
A11Y_TREE_ENV_VAR: str = "USE_A11Y_TREE"
TRIALS_ENV_VAR: str = "VLM_TRIALS"
TRIALS_MODELS_ENV_VAR: str = "VLM_TRIALS_MODELS"
COORD_SPACE_ENV_VAR: str = "COORD_SPACE"

# Coordinate conventions a model may answer in. "pixel" means absolute image
# pixels; "norm1000" means a resolution-independent 0-1000 grid that must be
# rescaled by the image dimensions before hit-testing.
#
# This is a manual override for models evaluation.providers does not already recognise.
# Models that self-describe their scale (see _uses_normalized_coords) report the
# convention per reply in the coord_space column instead; setting a non-pixel
# override for one of those is rejected rather than double-converted.
COORD_SPACES = ("pixel", "norm1000")
DEFAULT_COORD_SPACE = "pixel"

ALL_PROFILES = [
    "baseline",
    "elder_text_heavy",
    "elder_zoom_heavy",
    "elder_combo_max",
    "elder_combo_mid",
    "colorblind_deuteranomaly",
]


def resolve_models(cli_model: str | None) -> list[str]:
    """Resolve model precedence: CLI override, then VLM_MODEL env."""
    raw = ""
    if cli_model:
        raw = cli_model
    else:
        raw = os.environ.get(MODEL_ENV_VAR, "").strip()

    if raw:
        return [m.strip() for m in raw.split(",") if m.strip()]

    print(f"[ERROR] {MODEL_ENV_VAR} is not set.")
    print("")
    print("  To fix this, set a LiteLLM model string in .env, for example:")
    print("  VLM_MODEL=openai/gpt-4o-mini")
    print("")
    print("  Or set it in the environment for a single run:")
    print("  VLM_MODEL=openai/gpt-4o-mini agb evaluate")
    print("")
    print("  agb evaluate reads model configuration from .env.")
    raise SystemExit(1)


_A11Y_TREE_TRUE_VALUES = ("true", "1", "yes")
_A11Y_TREE_FALSE_VALUES = ("false", "0", "no", "")


def resolve_use_a11y_tree() -> bool:
    """Resolve the accessibility tree toggle from USE_A11Y_TREE env var.

    Returns True when the env var is set to a truthy value (true/1/yes),
    False when unset, empty, or a recognised falsy value (false/0/no).

    Unrecognised values exit rather than silently defaulting to False: a typo
    like USE_A11Y_TREE=on would otherwise run a full, expensive vision-only
    evaluation while the operator believes tree mode is active, with no
    _with_tree marker on the output file to reveal the mismatch afterwards.
    """
    raw = os.environ.get(A11Y_TREE_ENV_VAR, "").strip().lower()
    if raw in _A11Y_TREE_TRUE_VALUES:
        return True
    if raw in _A11Y_TREE_FALSE_VALUES:
        return False

    print(f"[ERROR] {A11Y_TREE_ENV_VAR} must be one of "
          f"{_A11Y_TREE_TRUE_VALUES + _A11Y_TREE_FALSE_VALUES}, got: {raw!r}")
    raise SystemExit(1)


def resolve_trials(model: str) -> int:
    """Resolve how many times each query is repeated for a given model.

    VLM_TRIALS sets the repeat count (default 1). VLM_TRIALS_MODELS optionally
    restricts repeats to a comma-separated subset of models, so budget can be
    spent on the models a claim depends on while the rest run once.

    Repeats do not increase statistical power; they measure how stable a single
    stochastic draw is, which is what lets a marginal result be defended as
    something other than sampling noise.
    """
    raw = os.environ.get(TRIALS_ENV_VAR, "").strip()
    if not raw:
        return 1

    try:
        trials = int(raw)
    except ValueError:
        print(f"[ERROR] {TRIALS_ENV_VAR} must be an integer, got: {raw}")
        raise SystemExit(1)

    if trials < 1:
        print(f"[ERROR] {TRIALS_ENV_VAR} must be >= 1, got: {raw}")
        raise SystemExit(1)

    subset = [
        m.strip()
        for m in os.environ.get(TRIALS_MODELS_ENV_VAR, "").split(",")
        if m.strip()
    ]
    if subset and model not in subset:
        return 1

    return trials


def resolve_coord_space() -> str:
    """Resolve the manual coordinate-convention override from COORD_SPACE.

    Models disagree on how to express a point. Most answer in absolute image
    pixels, but several (Qwen-VL, Gemini, GLM-V) answer on a 0-1000 grid
    regardless of the real image size. Scoring a normalized answer as pixels
    compresses every prediction into the top-left corner, which makes a hit
    arithmetically impossible and reports near-0% accuracy for an otherwise
    capable model.

    This is only an escape hatch for a model evaluation.providers does not yet
    recognise. Models matched by _uses_normalized_coords are prompted on the
    0-1000 scale and report the convention they actually answered in per reply,
    which is recorded in the coord_space column; combining that with a non-pixel
    override here would convert twice, so validate_coord_space rejects it.
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
