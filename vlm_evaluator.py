"""
vlm_evaluator.py
----------------
Command-line entrypoint for VLM grounding evaluation.

Runs fully offline against the saved dataset (no emulator required).

Usage:
  python vlm_evaluator.py                           # run full evaluation
  python vlm_evaluator.py --screens settings_main   # evaluate specific screens
  python vlm_evaluator.py --model openai/gpt-4o-mini # override model
"""

import argparse
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()  # loads .env from the project root into os.environ
except ImportError:
    pass  # python-dotenv optional; fall back to system env vars

import os
from vlm_eval.config import LABELS_DIR, get_results_csv, resolve_pace_seconds
from vlm_eval.results import init_csv
from vlm_eval.runner import evaluate_screen


def discover_screens() -> list[str]:
    """Auto-discover screen names from baseline label files."""
    screens = []
    if LABELS_DIR.is_dir():
        for f in sorted(LABELS_DIR.glob("*_baseline.json")):
            screen_name = f.stem.replace("_baseline", "")
            screens.append(screen_name)
    return screens


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="AccessGroundBench -- VLM Grounding Evaluator"
    )
    parser.add_argument(
        "--screens", nargs="+", default=None,
        help="Override the screen list (e.g., --screens settings_main dialer)",
    )
    parser.add_argument(
        "--models", nargs="+", 
        default=[
            "openai/gpt-4o-mini", 
            "gemini/gemini-2.5-flash", 
            "anthropic/claude-4.6-sonnet"
        ],
        help="List of LiteLLM models to run.",
    )
    parser.add_argument(
        "--pace-seconds", default=None,
        help=(
            "Optional delay after successful API calls. Overrides "
            "VLM_PACE_SECONDS. Default: 0"
        ),
    )
    return parser.parse_args()


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
    args = parse_args()
    pace_seconds = resolve_pace_seconds(args.pace_seconds)

    screens = args.screens if args.screens else discover_screens()
    if not screens:
        print("[ERROR] No screens found. Run orchestrator.py first to collect data.")
        sys.exit(1)

    print("=" * 60)
    print("  AccessGroundBench -- VLM Grounding Evaluator")
    print(f"  Models  : {', '.join(args.models)}")
    print(f"  Pace    : {pace_seconds}s")
    print(f"  Screens : {', '.join(screens)}")
    print("=" * 60)

    total_rows = 0
    for model in args.models:
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
