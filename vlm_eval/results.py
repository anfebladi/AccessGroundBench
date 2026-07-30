"""CSV result writing for VLM evaluation."""

import csv
from pathlib import Path

CSV_COLUMNS = [
    "screen", "target_text", "profile",
    "status",
    "raw_response", "x_pred", "y_pred",
    "x_min", "y_min", "x_max", "y_max",
    "score",
    "trials", "trial_scores", "parse_method",
    "prompt_mode", "tree_rows_sent",
]

# Row statuses. Only co_present rows carry a meaningful score; the others record
# why no grounding measurement exists, so that "the element is not on screen"
# is never silently counted as "the model looked in the wrong place".
STATUS_CO_PRESENT = "co_present"
STATUS_OFF_SCREEN = "off_screen"
STATUS_API_ERROR = "api_error"

# The element is still rendered somewhere in the modified layout, but its
# label text no longer matches the baseline string exactly -- reflow
# truncated or re-worded it (see vlm_eval.targets.locate_element). This is
# neither "the model looked in the wrong place" (co_present) nor "the element
# left the screen" (off_screen), so it gets its own status rather than being
# folded into either. Not queried or scored: whether/how to query it is an
# open sample-definition decision, not a settled part of the pipeline (see
# CLAUDE.md's remediation plan). No new CSV column is added for the matched
# text -- it is recorded in raw_response as "[LABEL-CHANGED: <matched text>]",
# following the existing sentinel convention derive_status already parses for
# "[OFF-SCREEN]" and "[API-ERROR...]", so no schema version bump is needed and
# resuming an in-progress run is unaffected.
STATUS_LABEL_CHANGED = "label_changed"

# The element is present on screen -- reachability must count it -- but its
# recorded box's center falls outside the screenshot, so hit_test has no
# valid point to score against (see bound_extractor.extract's clamping and
# vlm_eval.runner.evaluate_screen's defensive check). Not the model's fault
# and not a missing element, so it is neither co_present nor off_screen.
STATUS_OFF_FRAME = "off_frame"

# What prompt shape produced this row. The filename (evaluation_results_*.csv
# vs *_with_tree.csv) used to be the only record of this; putting it in the
# row itself lets a mixed file be detected instead of silently misread.
PROMPT_MODE_VISION = "vision"
PROMPT_MODE_TREE = "tree"


def init_csv(results_csv: Path) -> None:
    """Create the CSV file with headers, overwriting if it exists."""
    results_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(results_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_COLUMNS)
    print(f"  [CSV] Initialized {results_csv}")


def load_completed_keys(results_csv: Path) -> set[tuple[str, str, str]]:
    """
    Return the (screen, target_text, profile) keys already present in a CSV.

    Used to resume an interrupted run. Rows recording an API error are treated
    as incomplete so a transient provider failure is retried rather than frozen
    into the results.
    """
    if not results_csv.is_file():
        return set()

    completed: set[tuple[str, str, str]] = set()
    with open(results_csv, "r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if (row.get("status") or "") == STATUS_API_ERROR:
                continue
            completed.add((
                row.get("screen", ""),
                row.get("target_text", ""),
                row.get("profile", ""),
            ))
    return completed


def prepare_csv(
    results_csv: Path,
    fresh: bool = False,
    expected_prompt_mode: str | None = None,
) -> set[tuple[str, str, str]]:
    """
    Ready a results CSV for writing and report what is already done.

    With fresh=True (or no existing file) the CSV is recreated with headers and
    an empty set is returned. Otherwise the existing rows are kept and their
    keys returned so the runner can skip them.

    Resume matters because a full run is ~1000 paid API calls per model; the
    previous truncate-on-start behaviour discarded all of them on any crash.

    expected_prompt_mode, when given, guards against resuming into a mixed
    file: the resume key is (screen, target_text, profile) only, so a vision
    row would otherwise silently suppress the corresponding tree query (and
    vice versa) with nothing in the schema to reveal the mismatch afterwards.
    """
    if fresh or not results_csv.is_file():
        init_csv(results_csv)
        return set()

    completed = load_completed_keys(results_csv)

    # An existing file from before the status column was added cannot be
    # resumed safely, because its rows use a different schema.
    with open(results_csv, "r", newline="", encoding="utf-8") as f:
        header = next(csv.reader(f), [])
    if header != CSV_COLUMNS:
        print(f"  [CSV] {results_csv.name} uses an older schema; starting fresh.")
        init_csv(results_csv)
        return set()

    if expected_prompt_mode is not None:
        with open(results_csv, "r", newline="", encoding="utf-8") as f:
            modes_present = {
                row.get("prompt_mode")
                for row in csv.DictReader(f)
                if row.get("prompt_mode")
            }
        conflicting = modes_present - {expected_prompt_mode}
        if conflicting:
            raise ValueError(
                f"{results_csv} already contains prompt_mode={sorted(conflicting)} "
                f"rows, but this run is prompt_mode={expected_prompt_mode!r}. "
                "Vision and tree results must not share a file: resuming would "
                "silently skip queries whose (screen, target_text, profile) key "
                "already exists under the other mode. Use --fresh or a separate "
                "CSV path."
            )

    print(f"  [CSV] Resuming {results_csv} ({len(completed)} rows already done)")
    return completed


def append_result(results_csv: Path, row: dict) -> None:
    """Append a single evaluation result row to the CSV."""
    with open(results_csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([row.get(col, "") for col in CSV_COLUMNS])
