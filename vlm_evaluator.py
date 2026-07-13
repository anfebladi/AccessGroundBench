"""
vlm_evaluator.py
----------------
Command-line entrypoint for VLM grounding evaluation.

Runs fully offline against the saved dataset (no emulator required).

Usage:
  python vlm_evaluator.py                           # run full evaluation
"""

import os
import sys

from dotenv import load_dotenv

from vlm_eval.config import (
    LABELS_DIR,
    get_results_csv,
    resolve_model,
    resolve_pace_seconds,
)
from vlm_eval.results import init_csv
from vlm_eval.runner import evaluate_screen

load_dotenv()


def discover_screens() -> list[str]:
    """Auto-discover screen names from baseline label files."""
    screens = []
    if LABELS_DIR.is_dir():
        for f in sorted(LABELS_DIR.glob("*_baseline.json")):
            screen_name = f.stem.replace("_baseline", "")
            screens.append(screen_name)
    return screens



def _is_valid_key(key: str | None) -> bool:
    if not key:
        return False
    key_lower = key.lower()
    if "your-" in key_lower and "-here" in key_lower:
        return False
    return True


def api_key_exists(model_name: str) -> bool:
    if model_name.startswith("openai/"):
        return _is_valid_key(os.environ.get("OPENAI_API_KEY"))
    elif model_name.startswith("gemini/"):
        return _is_valid_key(os.environ.get("GEMINI_API_KEY")) or _is_valid_key(os.environ.get("GOOGLE_API_KEY"))
    elif model_name.startswith("anthropic/"):
        return _is_valid_key(os.environ.get("ANTHROPIC_API_KEY"))
    return True


def main() -> None:
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    
    model = resolve_model(None)
    models = [model]
    pace_seconds = resolve_pace_seconds(None)

    screens = discover_screens()
    if not screens:
        print("[ERROR] No screens found. Run orchestrator.py first to collect data.")
        sys.exit(1)

    print("=" * 60)
    print("  AccessGroundBench -- VLM Grounding Evaluator")
    print("  Mode    : OFFLINE evaluation from dataset/images + dataset/labels")
    print("  Note    : Does not navigate or capture the emulator")
    print(f"  Models  : {', '.join(models)}")
    print(f"  Pace    : {pace_seconds}s")
    print(f"  Screens : {', '.join(screens)}")
    print("=" * 60)

    total_rows = 0
    for model in models:
        if not api_key_exists(model):
            print(f"\n[SKIP] Missing API key for model: {model}")
            continue

        results_csv = get_results_csv(model)
        init_csv(results_csv)
        
        print(f"\n" + "=" * 60)
        print(f"  Evaluating Model: {model}")
        print(f"  Output CSV:       {results_csv}")
        print("=" * 60)

        for screen_name in screens:
            print(f"\n  -- Screen: {screen_name} --")
            rows = evaluate_screen(model, screen_name, pace_seconds, results_csv)
            total_rows += rows

    print("\n" + "=" * 60)
    print("  Evaluation complete!")
    print(f"  Total rows logged: {total_rows}")
    print("=" * 60)


if __name__ == "__main__":
    main()
