"""Complete VLM grounding evaluation workflow."""

import os
import sys

from dotenv import load_dotenv

from .config import (
    ALL_PROFILES,
    LABELS_DIR,
    get_results_csv,
    resolve_coord_space,
    resolve_models,
    resolve_pace_seconds,
    resolve_trials,
    resolve_use_a11y_tree,
)
from .results import (
    PROMPT_MODE_TREE,
    PROMPT_MODE_VISION,
    CsvLockError,
    acquire_lock,
    finalize_csv,
    has_data_rows,
    prepare_csv,
    release_lock,
)
from .runner import evaluate_screen, summarize_run
from .targets import build_expected_keys
from .providers import model_configuration_error, validate_coord_space

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


def evaluate(*, fresh: bool = False, force_unlock: bool = False) -> None:
    """Coordinate a complete evaluation run."""
    models = resolve_models(None)
    pace_seconds = resolve_pace_seconds(None)
    use_a11y_tree = resolve_use_a11y_tree()
    coord_space = resolve_coord_space()

    screens = discover_screens()
    if not screens:
        print("[ERROR] No screens found. Run 'agb collect' first to collect data.")
        sys.exit(1)

    # Computed once so every model's prepare_csv/finalize_csv call agrees on
    # exactly the same key set -- the canonical row count this collection
    # should produce (155 targets x 6 profiles as of this dataset).
    expected_key_order = build_expected_keys(screens, LABELS_DIR, ALL_PROFILES)
    expected_keys = set(expected_key_order)

    mode_label = "Vision + A11y Tree" if use_a11y_tree else "Vision-only"

    print("=" * 60)
    print("  AccessGroundBench -- VLM Grounding Evaluator")
    print(f"  Mode    : {mode_label}")
    print("  Note    : Does not navigate or capture the emulator")
    print(f"  Models  : {', '.join(models)}")
    print(f"  Coords  : {coord_space}")
    print(f"  Pace    : {pace_seconds}s")
    print(f"  Resume  : {'no (--fresh)' if fresh else 'yes'}")
    print(f"  Screens : {', '.join(screens)}")
    print("=" * 60)

    total_rows = 0
    all_problems: list[str] = []
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
        # COORD_SPACE is one global value but VLM_MODEL may list several
        # models, so it is validated per model: a non-pixel override on a
        # model that already reports its own scale would convert twice.
        coord_space = validate_coord_space(model, resolve_coord_space())

        print(f"\n" + "=" * 60)
        print(f"  Evaluating Model: {model}")
        print(f"  Output CSV:       {results_csv}")
        print(f"  Trials per query: {trials}")
        print("=" * 60)

        if force_unlock:
            release_lock(results_csv)
        try:
            # A second process against the same CSV used to snapshot
            # `completed` before this one had written anything and both
            # would append the same keys -- see CLAUDE.md's
            # canonicalization notes for the duplicate rows that caused.
            acquire_lock(results_csv)
        except CsvLockError as e:
            print(f"\n[SKIP] {e}")
            continue

        try:
            completed = prepare_csv(
                results_csv,
                fresh=fresh,
                expected_prompt_mode=PROMPT_MODE_TREE if use_a11y_tree else PROMPT_MODE_VISION,
                expected_keys=expected_keys,
            )

            for screen_name in screens:
                print(f"\n  -- Screen: {screen_name} --")
                rows = evaluate_screen(
                    model, screen_name, pace_seconds, results_csv,
                    use_a11y_tree=use_a11y_tree,
                    trials=trials,
                    completed=completed,
                    coord_space=coord_space,
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

            all_problems.extend(finalize_csv(results_csv, expected_key_order))
        finally:
            # init_csv writes the header before the first API call, so a run
            # that dies on call one leaves a header-only file named after the
            # model. mcnemar_analysis globs every evaluation_results_*.csv and
            # would treat that orphan as a real result, so drop it here.
            #
            # Keyed on the file being header-only, NOT on this run having
            # appended nothing: with resume, a re-run of an already-complete
            # model legitimately adds zero rows, and deleting then would
            # destroy a finished result.
            if results_csv.exists() and not has_data_rows(results_csv):
                results_csv.unlink()
                print(f"  [CSV] Removed empty results file: {results_csv.name}")
            release_lock(results_csv)

    print("\n" + "=" * 60)
    print("  Evaluation complete!")
    print(f"  Total rows logged this run: {total_rows}")
    print("=" * 60)

    if all_problems:
        print(f"\n  {len(all_problems)} PROBLEM(S) -- this dataset is not ready to use:")
        for problem in all_problems:
            print(f"    - {problem}")
        print("=" * 60)
        sys.exit(1)
