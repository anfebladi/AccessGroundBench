"""CSV result writing for VLM evaluation."""

import csv
from collections import Counter
from pathlib import Path

from backups import preserve
from .locking import CsvLockError, acquire_lock, release_lock

CSV_COLUMNS = [
    "screen", "target_text", "profile",
    "status",
    "raw_response", "x_pred", "y_pred",
    "x_min", "y_min", "x_max", "y_max",
    "score",
    "trials", "trial_scores", "parse_method",
    "prompt_mode", "tree_rows_sent",
    "coord_space",
    "image_sent_size",
]

# Per-row output-format compliance for models with their own coordinate
# convention (currently only Gemini; see evaluation.providers.GEMINI_SPACE_*). Blank
# for every other model and for rows that were never queried (off_screen,
# off_frame, label_changed, api_error) -- append_result's row.get(col, "")
# default covers those without every caller needing to pass the key.

# Row statuses. Only co_present rows carry a meaningful score; the others record
# why no grounding measurement exists, so that "the element is not on screen"
# is never silently counted as "the model looked in the wrong place".
STATUS_CO_PRESENT = "co_present"
STATUS_OFF_SCREEN = "off_screen"
STATUS_API_ERROR = "api_error"

# The element is still rendered somewhere in the modified layout, but its
# label text no longer matches the baseline string exactly -- reflow
# truncated or re-worded it (see evaluation.grounding.targets.locate_element). This is
# neither "the model looked in the wrong place" (co_present) nor "the element
# left the screen" (off_screen), so it gets its own status rather than being
# folded into either. Not queried or scored, since whether/how such a target
# should eventually be scored is a separate decision this pipeline does not
# make. No new CSV column is added for the matched text -- it is recorded in
# raw_response as "[LABEL-CHANGED: <matched text>]", following the existing
# sentinel convention derive_status already parses for "[OFF-SCREEN]" and
# "[API-ERROR...]", so no schema version bump is needed and resuming an
# in-progress run is unaffected.
STATUS_LABEL_CHANGED = "label_changed"

# The element is present on screen -- reachability must count it -- but its
# recorded box's center falls outside the screenshot, so hit_test has no
# valid point to score against (see bound_extractor.extract's clamping and
# evaluation.runner.evaluate_screen's defensive check). Not the model's fault
# and not a missing element, so it is neither co_present nor off_screen.
STATUS_OFF_FRAME = "off_frame"

# What prompt shape produced this row. The filename (evaluation_results_*.csv
# vs *_with_tree.csv) used to be the only record of this; putting it in the
# row itself lets a mixed file be detected instead of silently misread.
PROMPT_MODE_VISION = "vision"
PROMPT_MODE_TREE = "tree"


def canonicalize_rows(
    rows: list[dict],
    expected_keys: set[tuple[str, str, str]],
) -> tuple[list[dict], dict[str, int]]:
    """
    Reduce a results CSV's rows to exactly one per expected key.

    For each key, drops:
      - the row entirely, if its key is not in expected_keys (a stale
        target -- the harvested target set changed since this row was
        collected, e.g. evaluation.grounding.targets.invalid_targets excluding it after
        the fact);
      - every api_error row, once any real (non-api_error) row exists for
        that key -- api_error means the model was never actually asked the
        question on that attempt, so it carries no information once a real
        answer exists;
      - all but the FIRST real row, when a key has more than one -- kept
        deterministically by file order, never by score. Preferring a hit
        over a miss would bias accuracy upward exactly the way CLAUDE.md's
        remediation history warns against.

    A key with only api_error rows (never yet answered) loses all of them --
    it simply has zero rows afterward, indistinguishable from never having
    been attempted, so the very next run queries it again rather than
    resurrecting a placeholder failure.

    Returns (canonical_rows, counts) where counts breaks down what was
    dropped and why, for the caller to report. canonical_rows is sorted by
    each row's original position in `rows`; finalize_csv is what imposes the
    screen/profile/target canonical order for the final file.
    """
    by_key: dict[tuple[str, str, str], list[tuple[int, dict]]] = {}
    stale_target = 0

    for i, row in enumerate(rows):
        key = (row.get("screen", ""), row.get("target_text", ""), row.get("profile", ""))
        if key not in expected_keys:
            stale_target += 1
            continue
        by_key.setdefault(key, []).append((i, row))

    kept: list[tuple[int, dict]] = []
    dropped_api_error = 0
    dropped_duplicate_real = 0

    for items in by_key.values():
        real = [(i, r) for i, r in items if r.get("status") != STATUS_API_ERROR]
        dropped_api_error += len(items) - len(real)
        if not real:
            continue  # key never got a real answer; retry, don't fabricate one
        first_i, first_row = min(real, key=lambda ir: ir[0])
        dropped_duplicate_real += len(real) - 1
        kept.append((first_i, first_row))

    kept.sort(key=lambda ir: ir[0])
    canonical_rows = [row for _i, row in kept]
    counts = {
        "stale_target": stale_target,
        "api_error": dropped_api_error,
        "duplicate": dropped_duplicate_real,
    }
    return canonical_rows, counts


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
    expected_keys: set[tuple[str, str, str]] | None = None,
) -> set[tuple[str, str, str]]:
    """Ready a results CSV for writing and report what is already done.

    With fresh=True (or no existing file) the CSV is recreated with headers
    and an empty set is returned. Otherwise the existing rows are kept and
    their keys returned so the runner can skip them -- a full run is ~1000
    paid API calls per model, so resuming matters.

    Every path that discards rows preserves the file under .backups/ first
    (src/backups.py), including the schema-mismatch path below, which is
    reached by an ordinary resume rather than by anything the caller asked
    for.

    When expected_keys is given, the file is canonicalized against it first
    (see canonicalize_rows): stale-target rows, superseded api_error rows,
    and duplicate copies of the same key are dropped, with the original
    preserved under .backups/ first. Without this, a key whose only surviving
    copy (after whatever order retries happened to land in) is a stale
    api_error silently drops out of every downstream analysis that indexes by
    key -- see CLAUDE.md's canonicalization notes for the case this caught.
    """
    # expected_prompt_mode, when given, guards against resuming into a mixed
    # file: the resume key is (screen, target_text, profile) only, so a
    # vision row would otherwise silently suppress the corresponding tree
    # query (and vice versa) with nothing in the schema to reveal the
    # mismatch afterwards.
    if fresh or not results_csv.is_file():
        # --fresh is explicit, but what it discards is still ~930 rows of paid
        # API calls; keep a copy so a mistyped command is recoverable.
        preserve(results_csv, reason="--fresh discards the existing rows")
        init_csv(results_csv)
        return set()

    completed = load_completed_keys(results_csv)

    # An existing file whose columns don't match CSV_COLUMNS is either a
    # purely-additive upgrade (older CSVs are missing only trailing columns
    # added since, e.g. coord_space -- every existing row just reads back
    # as "" for those) or a genuinely incompatible schema (a rename,
    # reorder, or removal). Only the latter cannot be resumed safely.
    with open(results_csv, "r", newline="", encoding="utf-8") as f:
        header = next(csv.reader(f), [])
    is_additive_upgrade = (
        bool(header)
        and len(header) < len(CSV_COLUMNS)
        and CSV_COLUMNS[: len(header)] == header
    )
    if header != CSV_COLUMNS and not is_additive_upgrade:
        # Nobody asked for this: an ordinary resume hits it whenever a column
        # was renamed, reordered, or removed since the file was written. It
        # discards every row -- the most expensive data the pipeline produces
        # -- so the copy has to happen before init_csv truncates.
        preserve(results_csv, reason="schema is not resumable; rows would be lost")
        print(f"  [CSV] {results_csv.name} uses an older schema; starting fresh.")
        init_csv(results_csv)
        return set()
    if is_additive_upgrade:
        print(
            f"  [CSV] {results_csv.name} predates column(s) "
            f"{', '.join(CSV_COLUMNS[len(header):])}; resuming without "
            "wiping it -- existing rows read as blank for the new column(s)."
        )

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

    if expected_keys is not None:
        with open(results_csv, "r", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        canonical_rows, counts = canonicalize_rows(rows, expected_keys)
        if any(counts.values()) or is_additive_upgrade:
            preserve(results_csv, reason="canonicalization rewrites the file")
            with open(results_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(CSV_COLUMNS)
                for row in canonical_rows:
                    writer.writerow([row.get(col, "") for col in CSV_COLUMNS])
            print(
                f"  [CSV] Canonicalized {results_csv.name}: dropped "
                f"{counts['stale_target']} stale-target row(s), "
                f"{counts['api_error']} api_error row(s), "
                f"{counts['duplicate']} duplicate real row(s)"
            )
            # completed was derived from the file before this rewrite, but
            # canonicalization never changes key membership: it only removes
            # extra copies of keys already counted, or api_error-only keys
            # that load_completed_keys already excluded -- so it stays valid
            # without recomputing.

    print(f"  [CSV] Resuming {results_csv} ({len(completed)} rows already done)")
    return completed


def append_result(results_csv: Path, row: dict) -> None:
    """Append a single evaluation result row to the CSV."""
    with open(results_csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([row.get(col, "") for col in CSV_COLUMNS])


def has_data_rows(results_csv: Path) -> bool:
    """Return True when the CSV holds at least one row beyond its header.

    init_csv writes the header before the first API call, so a run that dies on
    call one leaves a header-only orphan named after the model.
    discover_result_csvs globs every evaluation_results_*.csv and would treat
    that orphan as a real result, so the caller deletes it.

    Deliberately keyed on file content rather than on how many rows a given run
    appended: resume means a re-run of an already-complete model adds nothing,
    and that file must survive.
    """
    try:
        with open(results_csv, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)  # header
            return any(row for row in reader)
    except FileNotFoundError:
        return False


def finalize_csv(
    results_csv: Path,
    expected_key_order: list[tuple[str, str, str]],
) -> list[str]:
    """
    Verify a finished results CSV against its expected key set and sort it.

    Mirrors orchestrator.write_manifest's contract: returns a list of problem
    strings (empty means clean) rather than raising, so a caller running
    several models can finish all of them and report every gap at once
    instead of aborting at the first.

    Checks, all against expected_key_order taken as authoritative:
      - every expected key has exactly one row (missing keys are reported;
        typically means the run was interrupted or a query never completed);
      - no key appears more than once (would mean two writers raced past the
        lock, or canonicalize_rows/finalize_csv itself has a bug);
      - no row still has status=api_error (would mean canonicalize_rows was
        never run against this file, or a row was appended after it).

    On a clean file, rewrites it sorted into expected_key_order -- screen,
    then profile, then target (see evaluation.grounding.targets.build_expected_keys) --
    so two independent collection runs produce byte-comparable files instead
    of one whose row order is an artifact of resume history.
    """
    problems: list[str] = []
    expected_set = set(expected_key_order)

    if not results_csv.is_file():
        return [f"{results_csv.name}: file does not exist"]

    with open(results_csv, "r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    by_key: dict[tuple[str, str, str], list[dict]] = {}
    for row in rows:
        key = (row.get("screen", ""), row.get("target_text", ""), row.get("profile", ""))
        by_key.setdefault(key, []).append(row)

    missing = [k for k in expected_key_order if k not in by_key]
    unexpected = [k for k in by_key if k not in expected_set]
    duplicated = {k: v for k, v in by_key.items() if len(v) > 1}
    error_rows = [r for r in rows if r.get("status") == STATUS_API_ERROR]

    if missing:
        problems.append(
            f"{results_csv.name}: {len(missing)} expected key(s) have no row "
            f"(e.g. {missing[0]}) -- collection is incomplete for this model"
        )
    if unexpected:
        problems.append(
            f"{results_csv.name}: {len(unexpected)} row(s) have a key outside "
            f"the expected target set (e.g. {next(iter(unexpected))}) -- "
            "run canonicalize_rows/prepare_csv against the current target set"
        )
    if duplicated:
        example = next(iter(duplicated))
        problems.append(
            f"{results_csv.name}: {len(duplicated)} key(s) have more than one "
            f"row (e.g. {example} x{len(duplicated[example])}) -- two writers "
            "may have raced past the lock, or canonicalize_rows was skipped"
        )
    if error_rows:
        problems.append(
            f"{results_csv.name}: {len(error_rows)} row(s) still have "
            "status=api_error -- canonicalize_rows was not run, or a query "
            "failed after finalize_csv's last pass"
        )

    if problems:
        return problems

    with open(results_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_COLUMNS)
        for key in expected_key_order:
            row = by_key[key][0]
            writer.writerow([row.get(col, "") for col in CSV_COLUMNS])

    return []
