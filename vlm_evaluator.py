"""
vlm_evaluator.py
----------------
Command-line entrypoint for VLM grounding evaluation.

Runs fully offline against the saved dataset (no emulator required).

Usage:
  python vlm_evaluator.py                # run (resumes an interrupted run)
  python vlm_evaluator.py --fresh        # discard existing rows and restart
"""

import argparse
import os
import sys

from dotenv import load_dotenv

from vlm_eval.config import (
    LABELS_DIR,
    get_results_csv,
    resolve_models,
    resolve_pace_seconds,
    resolve_trials,
    resolve_use_a11y_tree,
)
from vlm_eval.results import PROMPT_MODE_TREE, PROMPT_MODE_VISION, prepare_csv
from vlm_eval.runner import evaluate_screen, summarize_run
from vlm_provider import model_configuration_error

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
    if model_name.startswith(("9router/", "openai_compatible/")):
        return model_configuration_error(model_name) is None
    if model_name.startswith("openai/"):
        return _is_valid_key(os.environ.get("OPENAI_API_KEY"))
    elif model_name.startswith("gemini/"):
        return _is_valid_key(os.environ.get("GEMINI_API_KEY")) or _is_valid_key(os.environ.get("GOOGLE_API_KEY"))
    elif model_name.startswith("anthropic/"):
        return _is_valid_key(os.environ.get("ANTHROPIC_API_KEY"))
    return True


def main(argv: list[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding='utf-8')

    parser = argparse.ArgumentParser(
        description="AccessGroundBench -- VLM grounding evaluator"
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Discard existing result rows and restart from scratch "
             "(default resumes an interrupted run)",
    )
    args = parser.parse_args(argv)

    models = resolve_models(None)
    pace_seconds = resolve_pace_seconds(None)
    use_a11y_tree = resolve_use_a11y_tree()

    screens = discover_screens()
    if not screens:
        print("[ERROR] No screens found. Run orchestrator.py first to collect data.")
        sys.exit(1)

    mode_label = "Vision + A11y Tree" if use_a11y_tree else "Vision-only"

    print("=" * 60)
    print("  AccessGroundBench -- VLM Grounding Evaluator")
    print(f"  Mode    : {mode_label}")
    print("  Note    : Does not navigate or capture the emulator")
    print(f"  Models  : {', '.join(models)}")
    print(f"  Pace    : {pace_seconds}s")
    print(f"  Resume  : {'no (--fresh)' if args.fresh else 'yes'}")
    print(f"  Screens : {', '.join(screens)}")
    print("=" * 60)

    total_rows = 0
    for model in models:
        if not api_key_exists(model):
            config_error = model_configuration_error(model)
            if config_error:
                print(f"\n[SKIP] {config_error}")
            else:
                print(f"\n[SKIP] Missing API key for model: {model}")
            continue

        results_csv = get_results_csv(model, use_a11y_tree)
        trials = resolve_trials(model)

        print(f"\n" + "=" * 60)
        print(f"  Evaluating Model: {model}")
        print(f"  Output CSV:       {results_csv}")
        print(f"  Trials per query: {trials}")
        print("=" * 60)

        completed = prepare_csv(
            results_csv,
            fresh=args.fresh,
            expected_prompt_mode=PROMPT_MODE_TREE if use_a11y_tree else PROMPT_MODE_VISION,
        )

        for screen_name in screens:
            print(f"\n  -- Screen: {screen_name} --")
            rows = evaluate_screen(
                model, screen_name, pace_seconds, results_csv,
                use_a11y_tree=use_a11y_tree,
                trials=trials,
                completed=completed,
            )
            total_rows += rows

        summary = summarize_run(results_csv)
        if summary:
            print(f"\n  [SUMMARY] {model}")
            for status, count in sorted(summary["statuses"].items()):
                print(f"    {status or '(blank)':<14} {count}")
            print(f"    parse failures {summary['parse_failures']}")
            if summary["flip_rate"] is not None:
                print(f"    trial flip rate {summary['flip_rate'] * 100:.1f}% "
                      f"({summary['flipped_rows']}/{summary['multi_trial_rows']} "
                      f"multi-trial targets disagreed)")

    print("\n" + "=" * 60)
    print("  Evaluation complete!")
    print(f"  Total rows logged this run: {total_rows}")
    print("=" * 60)


if __name__ == "__main__":
    main()
