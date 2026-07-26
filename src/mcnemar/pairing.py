"""CSV loading and paired-sample construction for McNemar analyses."""

import csv
import sys
from collections import defaultdict
from pathlib import Path


def load_results(csv_path: Path) -> list[dict]:
    """Load the evaluation results CSV into a list of row dicts."""
    if not csv_path.is_file():
        print(f"[ERROR] Results CSV not found: {csv_path}")
        sys.exit(1)

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"[LOADED] {len(rows)} rows from {csv_path}")
    return rows


def tracking_key(screen: str, target_text: str) -> str:
    """Build the legacy tracking key used to pair scores across profiles."""
    return f"{screen}_{target_text}"


def build_pairs(rows: list[dict]) -> dict[str, dict[str, int]]:
    """Reorganize flat CSV rows into profile scores keyed by tracking key."""
    pairs: dict[str, dict[str, int]] = defaultdict(dict)

    for row in rows:
        screen = row.get("screen", "")
        text = row.get("target_text", "")
        profile = row.get("profile", "")
        score = int(row.get("score", 0))

        pairs[tracking_key(screen, text)][profile] = score

    return dict(pairs)


def compute_contingency(
    pairs: dict[str, dict[str, int]],
    experimental_profile: str,
) -> tuple[int, int, int, int]:
    """Compile the baseline-versus-profile 2x2 contingency matrix."""
    return _compute_contingency(
        (
            (scores.get("baseline"), scores.get(experimental_profile))
            for scores in pairs.values()
        )
    )


def build_cross_file_pairs(
    rows_a: list[dict],
    rows_b: list[dict],
) -> dict[str, dict[str, tuple[int, int]]]:
    """Build same-profile score pairs across two evaluation-result CSV files."""
    index_a = _index_rows(rows_a)
    index_b = _index_rows(rows_b)

    pairs: dict[str, dict[str, tuple[int, int]]] = defaultdict(dict)
    all_keys = set(index_a.keys()) | set(index_b.keys())

    for screen, target_text, profile in all_keys:
        score_a = index_a.get((screen, target_text, profile))
        score_b = index_b.get((screen, target_text, profile))
        if score_a is not None and score_b is not None:
            pairs[tracking_key(screen, target_text)][profile] = (score_a, score_b)

    return dict(pairs)


def compute_cross_contingency(
    pairs: dict[str, dict[str, tuple[int, int]]],
    profile: str,
) -> tuple[int, int, int, int]:
    """Compile the file-A-versus-file-B 2x2 contingency matrix for a profile."""
    return _compute_contingency(
        (profile_scores.get(profile, (None, None)) for profile_scores in pairs.values())
    )


def _index_rows(rows: list[dict]) -> dict[tuple[str, str, str], int]:
    """Index rows using the legacy overwrite-on-duplicate behavior."""
    index: dict[tuple[str, str, str], int] = {}
    for row in rows:
        key = (row.get("screen", ""), row.get("target_text", ""), row.get("profile", ""))
        index[key] = int(row.get("score", 0))
    return index


def _compute_contingency(
    score_pairs: object,
) -> tuple[int, int, int, int]:
    """Count paired binary scores, skipping pairs missing either score."""
    a = b = c = d = 0

    for first_score, second_score in score_pairs:
        if first_score is None or second_score is None:
            continue

        if first_score == 1 and second_score == 1:
            a += 1
        elif first_score == 1 and second_score == 0:
            b += 1
        elif first_score == 0 and second_score == 1:
            c += 1
        else:
            d += 1

    return a, b, c, d
