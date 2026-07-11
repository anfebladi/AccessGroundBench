"""CSV result writing for VLM evaluation."""

import csv
from pathlib import Path

CSV_COLUMNS = [
    "screen", "target_text", "profile",
    "raw_response", "x_pred", "y_pred",
    "x_min", "y_min", "x_max", "y_max",
    "score",
]


def init_csv(results_csv: Path) -> None:
    """Create the CSV file with headers, overwriting if it exists."""
    results_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(results_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_COLUMNS)
    print(f"  [CSV] Initialized {results_csv}")


def append_result(results_csv: Path, row: dict) -> None:
    """Append a single evaluation result row to the CSV."""
    with open(results_csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([row.get(col, "") for col in CSV_COLUMNS])
