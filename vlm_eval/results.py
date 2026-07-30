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
]

# Row statuses. Only co_present rows carry a meaningful score; the others record
# why no grounding measurement exists, so that "the element is not on screen"
# is never silently counted as "the model looked in the wrong place".
STATUS_CO_PRESENT = "co_present"
STATUS_OFF_SCREEN = "off_screen"
STATUS_API_ERROR = "api_error"


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


def prepare_csv(results_csv: Path, fresh: bool = False) -> set[tuple[str, str, str]]:
    """
    Ready a results CSV for writing and report what is already done.

    With fresh=True (or no existing file) the CSV is recreated with headers and
    an empty set is returned. Otherwise the existing rows are kept and their
    keys returned so the runner can skip them.

    Resume matters because a full run is ~1000 paid API calls per model; the
    previous truncate-on-start behaviour discarded all of them on any crash.
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

    print(f"  [CSV] Resuming {results_csv} ({len(completed)} rows already done)")
    return completed


def append_result(results_csv: Path, row: dict) -> None:
    """Append a single evaluation result row to the CSV."""
    with open(results_csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([row.get(col, "") for col in CSV_COLUMNS])
