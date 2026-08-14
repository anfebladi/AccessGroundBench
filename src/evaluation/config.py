"""Configuration and project paths for VLM evaluation."""

import os
from pathlib import Path

from paths import DATASET_DIR, evaluation_results_path

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


def reject_colliding_models(models: list[str]) -> None:
    """Fail when two routed ids in one run reduce to the same result filename.

    Stripping the routing prefix means routed model ids can share a result
    filename. Left alone the second model would *resume* against the first
    one's rows, silently blending two models' answers into one file that still
    looks well-formed.
    Refusing up front costs a rename; not refusing costs the run.
    """
    from collections import defaultdict

    by_filename: dict[str, list[str]] = defaultdict(list)
    for model in models:
        by_filename[sanitize_model_filename(model)].append(model)

    collisions = {name: ids for name, ids in by_filename.items() if len(ids) > 1}
    if not collisions:
        return

    print("[ERROR] Two models in this run resolve to the same result filename:")
    for name, ids in sorted(collisions.items()):
        print(f"  {name}_<mode>.csv  <-  {', '.join(ids)}")
    print("")
    print("  Result files are named after the model, not the route it was")
    print("  reached through, so these would share one resumable CSV.")
    print(f"  Run them separately, or drop one from {MODEL_ENV_VAR}.")
    raise SystemExit(1)


def resolve_models(cli_model: str | None) -> list[str]:
    """Resolve model precedence: CLI override, then VLM_MODEL env."""
    raw = ""
    if cli_model:
        raw = cli_model
    else:
        raw = os.environ.get(MODEL_ENV_VAR, "").strip()

    if raw:
        models = [m.strip() for m in raw.split(",") if m.strip()]
        reject_colliding_models(models)
        return models

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
    `_tree` marker on the output file to reveal the mismatch afterwards.
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


# Characters illegal (or merely troublesome) in a Windows filename, beyond
# '/' which is handled separately to keep existing result filenames stable.
# Control characters are covered by the range check in sanitize_model_filename.
_WINDOWS_ILLEGAL_CHARS = '<>:"\\|?*'
_MAX_CLEAN_MODEL_LENGTH = 150


# Prefixes that name *how a request was routed*, not what model answered it.
# 9router is a shim: the same GPT or Gemini model reachable through a
# different gateway is still that model, and the gateway is a local
# deployment detail nobody else shares.
_ROUTING_PREFIXES = ("9router/",)


def canonical_model_id(model: str) -> str:
    """Reduce a routed model id to the model it actually identifies.

    ``9router/cx/gpt-5.6-sol`` -> ``gpt-5.6-sol``.

    Provider-prefixed ids (``anthropic/``, ``openai/``, ``gemini/``,
    ``local/``) are returned unchanged -- those name who serves the model,
    which is a real property of the result, not a routing accident.

    Only the published identity changes. VLM_MODEL still takes the full routed
    id, and the routing layer
    (``evaluation.providers.config``) never sees this function's output --
    ``resolve_completion_config`` and ``uses_normalized_coords`` must keep
    reading the raw id or requests would go to the wrong endpoint.
    """
    for prefix in _ROUTING_PREFIXES:
        if model.startswith(prefix):
            remainder = model[len(prefix):].strip("/")
            # A prefix with nothing after it is malformed; leave it intact so
            # model_configuration_error reports it rather than silently
            # collapsing every broken id to the same empty name.
            return remainder.rsplit("/", 1)[-1] if remainder else model
    return model


def sanitize_model_filename(model: str) -> str:
    """Turn a model id into a safe Windows filename component.

    A bare '/' -> '_' substitution is not enough for bring-your-own model ids:
    Ollama and Bedrock ids commonly contain ':' (e.g.
    "ollama/llama3.2-vision:11b"), which is illegal in a Windows filename and
    crashes at file-open time with no indication of why.

    Routing prefixes are stripped first (see canonical_model_id), so a result
    file is named after the model rather than the gateway it was reached
    through.
    """
    cleaned = canonical_model_id(model).replace("/", "_")
    cleaned = "".join(
        "_" if ch in _WINDOWS_ILLEGAL_CHARS or ord(ch) < 32 else ch
        for ch in cleaned
    )
    # Windows silently strips trailing dots/spaces from filenames, which
    # would make two distinct model ids collide on disk.
    cleaned = cleaned.rstrip(". ")
    if not cleaned:
        cleaned = "_"
    return cleaned[:_MAX_CLEAN_MODEL_LENGTH]


def get_results_csv(model: str, use_a11y_tree: bool = False) -> Path:
    """Return the result file for *model* under the active dataset's outputs.

    Scoped to DATASET_DIR (so AGB_DATASET_DIR carries through) rather than to a
    single shared directory: two datasets evaluating the same model must not
    reach the same file, or the second run would resume against the first
    run's completed keys.
    """
    return evaluation_results_path(model, use_a11y_tree)
