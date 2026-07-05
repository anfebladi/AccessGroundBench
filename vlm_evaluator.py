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

from vlm_eval.config import LABELS_DIR, RESULTS_CSV, resolve_model, resolve_pace_seconds
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
        "--model", default=None,
        help=(
            "LiteLLM model string to use. Overrides VLM_MODEL. "
            "Required if VLM_MODEL is not set."
        ),
    )
    parser.add_argument(
        "--pace-seconds", default=None,
        help=(
            "Optional delay after successful API calls. Overrides "
            "VLM_PACE_SECONDS. Default: 0"
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    model = resolve_model(args.model)
    pace_seconds = resolve_pace_seconds(args.pace_seconds)

    screens = args.screens if args.screens else discover_screens()
    if not screens:
        print("[ERROR] No screens found. Run orchestrator.py first to collect data.")
        sys.exit(1)

    print("=" * 60)
    print("  AccessGroundBench -- VLM Grounding Evaluator")
    print(f"  Model   : {model}")
    print(f"  Pace    : {pace_seconds}s")
    print(f"  Screens : {', '.join(screens)}")
    print(f"  CSV     : {RESULTS_CSV}")
    print("=" * 60)

    init_csv(RESULTS_CSV)

    total_rows = 0
    for screen_name in screens:
        print(f"\n{'=' * 60}")
        print(f"  Evaluating screen: {screen_name}")
        print(f"{'=' * 60}")
        rows = evaluate_screen(model, screen_name, pace_seconds)
        total_rows += rows

    print("\n" + "=" * 60)
    print("  Evaluation complete!")
    print(f"  Total rows logged: {total_rows}")
    print(f"  Results CSV: {RESULTS_CSV}")
    print("=" * 60)


if __name__ == "__main__":
    main()
