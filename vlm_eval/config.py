"""Configuration and project paths for VLM evaluation."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = PROJECT_ROOT / "dataset"
IMAGES_DIR = DATASET_DIR / "images"
LABELS_DIR = DATASET_DIR / "labels"

MODEL_ENV_VAR: str = "VLM_MODEL"
PACE_ENV_VAR: str = "VLM_PACE_SECONDS"

ALL_PROFILES = [
    "baseline",
    "elder_text_heavy",
    "elder_zoom_heavy",
    "elder_combo_max",
    "elder_combo_rtl",
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
    print("  Or pass a temporary override:")
    print("  python vlm_evaluator.py --model openai/gpt-4o-mini")
    raise SystemExit(1)


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


def get_results_csv(model: str) -> Path:
    """Generate a dynamic CSV path based on the model name."""
    clean_model = model.replace("/", "_")
    return DATASET_DIR / f"evaluation_results_{clean_model}.csv"
