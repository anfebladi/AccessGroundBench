import csv
import tempfile
import unittest
from pathlib import Path

from backups import BACKUP_DIR_NAME
from evaluation.storage.results import (
    CSV_COLUMNS,
    PROMPT_MODE_TREE,
    PROMPT_MODE_VISION,
    STATUS_API_ERROR,
    STATUS_CO_PRESENT,
    CsvLockError,
    acquire_lock,
    append_result,
    canonicalize_rows,
    finalize_csv,
    init_csv,
    load_completed_keys,
    prepare_csv,
    release_lock,
)


def sample_row(**overrides) -> dict:
    row = {
        "screen": "clock",
        "target_text": "Timer",
        "profile": "baseline",
        "status": STATUS_CO_PRESENT,
        "raw_response": "[1, 2]",
        "x_pred": 1,
        "y_pred": 2,
        "x_min": 0,
        "y_min": 0,
        "x_max": 10,
        "y_max": 10,
        "score": 1,
        "trials": 1,
        "trial_scores": "1",
        "parse_method": "bracket",
        "prompt_mode": PROMPT_MODE_VISION,
        "tree_rows_sent": 0,
    }
    row.update(overrides)
    return row


class VlmEvalResultsTests(unittest.TestCase):
    def test_init_csv_writes_header_once(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "evaluation_results.csv"

            init_csv(csv_path)
            init_csv(csv_path)

            with open(csv_path, "r", encoding="utf-8", newline="") as f:
                rows = list(csv.reader(f))

        self.assertEqual([CSV_COLUMNS], rows)

    def test_append_result_preserves_column_order(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "evaluation_results.csv"
            init_csv(csv_path)
            append_result(csv_path, sample_row())

            with open(csv_path, "r", encoding="utf-8", newline="") as f:
                rows = list(csv.reader(f))

        self.assertEqual(CSV_COLUMNS, rows[0])
        self.assertEqual(
            ["clock", "Timer", "baseline", STATUS_CO_PRESENT, "[1, 2]", "1", "2",
             "0", "0", "10", "10", "1", "1", "1", "bracket", PROMPT_MODE_VISION, "0", ""],
            rows[1],
        )


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.csv_path = Path(self.tmp.name) / "evaluation_results.csv"

    def test_prepare_csv_creates_file_when_absent(self):
        completed = prepare_csv(self.csv_path)

        self.assertEqual(set(), completed)
        self.assertTrue(self.csv_path.is_file())

    def test_prepare_csv_returns_completed_keys_and_keeps_rows(self):
        init_csv(self.csv_path)
        append_result(self.csv_path, sample_row())
        append_result(self.csv_path, sample_row(target_text="Alarm", profile="elder_combo_max"))

        completed = prepare_csv(self.csv_path)

        self.assertEqual(
            {("clock", "Timer", "baseline"), ("clock", "Alarm", "elder_combo_max")},
            completed,
        )
        with open(self.csv_path, "r", encoding="utf-8", newline="") as f:
            self.assertEqual(3, len(list(csv.reader(f))))  # header + 2 rows

    def test_prepare_csv_fresh_discards_existing_rows(self):
        init_csv(self.csv_path)
        append_result(self.csv_path, sample_row())

        completed = prepare_csv(self.csv_path, fresh=True)

        self.assertEqual(set(), completed)
        with open(self.csv_path, "r", encoding="utf-8", newline="") as f:
            self.assertEqual(1, len(list(csv.reader(f))))  # header only

    def test_api_error_rows_are_retried_not_treated_as_done(self):
        init_csv(self.csv_path)
        append_result(self.csv_path, sample_row(status=STATUS_API_ERROR, score=""))

        self.assertEqual(set(), load_completed_keys(self.csv_path))

    def test_prepare_csv_allows_resuming_matching_prompt_mode(self):
        init_csv(self.csv_path)
        append_result(self.csv_path, sample_row(prompt_mode=PROMPT_MODE_VISION))

        completed = prepare_csv(
            self.csv_path, expected_prompt_mode=PROMPT_MODE_VISION
        )

        self.assertEqual({("clock", "Timer", "baseline")}, completed)

    def test_prepare_csv_rejects_resuming_into_mixed_prompt_mode_file(self):
        # Resume keys on (screen, target_text, profile) only, so a vision row
        # would otherwise silently suppress the corresponding tree query for
        # the same key (and vice versa) with nothing in the schema to reveal
        # the mismatch afterwards.
        init_csv(self.csv_path)
        append_result(self.csv_path, sample_row(prompt_mode=PROMPT_MODE_VISION))

        with self.assertRaisesRegex(ValueError, "prompt_mode"):
            prepare_csv(self.csv_path, expected_prompt_mode=PROMPT_MODE_TREE)

    def test_prepare_csv_expected_prompt_mode_is_optional(self):
        # Callers that don't pass expected_prompt_mode (e.g. pre-existing
        # scripts) keep the old unguarded resume behaviour.
        init_csv(self.csv_path)
        append_result(self.csv_path, sample_row(prompt_mode=PROMPT_MODE_TREE))

        completed = prepare_csv(self.csv_path)

        self.assertEqual({("clock", "Timer", "baseline")}, completed)

    def test_additive_schema_upgrade_is_resumed_not_wiped(self):
        # CSV_COLUMNS has grown by appending columns (prompt_mode,
        # tree_rows_sent, coord_space); a file missing only trailing
        # columns like this must be resumed, not silently reinitialized --
        # canonicalize_results.py's dry run against a real gpt-5.4_with_tree
        # file caught this wiping 1353 real rows before this fix existed.
        old_columns = CSV_COLUMNS[:-1]  # missing only coord_space
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(old_columns)
            writer.writerow([
                "clock", "Timer", "baseline", STATUS_CO_PRESENT, "[1, 2]",
                "1", "2", "0", "0", "10", "10", "1", "1", "1", "bracket",
                PROMPT_MODE_VISION, "0",
            ])

        completed = prepare_csv(self.csv_path)

        self.assertEqual({("clock", "Timer", "baseline")}, completed)
        with open(self.csv_path, "r", newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        self.assertEqual(2, len(rows))  # header + the one real row, untouched

    def test_older_schema_is_restarted_rather_than_resumed(self):
        # A pre-status CSV cannot be resumed safely: its columns differ.
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["screen", "target_text", "profile", "score"])
            writer.writerow(["clock", "Timer", "baseline", "1"])

        completed = prepare_csv(self.csv_path)

        self.assertEqual(set(), completed)
        with open(self.csv_path, "r", encoding="utf-8", newline="") as f:
            self.assertEqual([CSV_COLUMNS], list(csv.reader(f)))


class LockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.csv_path = Path(self.tmp.name) / "evaluation_results.csv"

    def test_acquire_lock_then_second_acquire_raises(self):
        acquire_lock(self.csv_path)
        with self.assertRaisesRegex(CsvLockError, "locked by another run"):
            acquire_lock(self.csv_path)

    def test_release_then_reacquire_succeeds(self):
        acquire_lock(self.csv_path)
        release_lock(self.csv_path)
        acquire_lock(self.csv_path)  # must not raise

    def test_release_lock_is_a_no_op_when_no_lock_exists(self):
        release_lock(self.csv_path)  # must not raise


class CanonicalizeRowsTests(unittest.TestCase):
    def test_keeps_first_real_row_when_a_key_is_duplicated(self):
        expected = {("clock", "Timer", "baseline")}
        rows = [
            sample_row(x_pred=1),
            sample_row(x_pred=2),
        ]
        canonical, counts = canonicalize_rows(rows, expected)

        self.assertEqual(1, len(canonical))
        self.assertEqual(1, canonical[0]["x_pred"])
        self.assertEqual(1, counts["duplicate"])
        self.assertEqual(0, counts["api_error"])
        self.assertEqual(0, counts["stale_target"])

    def test_prefers_real_row_over_a_later_api_error(self):
        # The exact shape found in gpt-5.4_with_tree.csv: a real answer,
        # then a stale api_error appended by a later resumed/retried run.
        expected = {("clock", "Timer", "baseline")}
        real = sample_row(score=1)
        error = sample_row(status=STATUS_API_ERROR, score="", raw_response="[API-ERROR: RateLimitError]")
        canonical, counts = canonicalize_rows([real, error], expected)

        self.assertEqual([real], canonical)
        self.assertEqual(1, counts["api_error"])

    def test_prefers_real_row_over_an_earlier_api_error(self):
        expected = {("clock", "Timer", "baseline")}
        error = sample_row(status=STATUS_API_ERROR, score="", raw_response="[API-ERROR: RateLimitError]")
        real = sample_row(score=1)
        canonical, counts = canonicalize_rows([error, real], expected)

        self.assertEqual([real], canonical)
        self.assertEqual(1, counts["api_error"])

    def test_key_with_only_api_error_rows_is_dropped_entirely(self):
        # Zero rows afterward is indistinguishable from never having been
        # attempted -- the next run must re-query it, not resurrect a
        # placeholder failure.
        expected = {("clock", "Timer", "baseline")}
        error = sample_row(status=STATUS_API_ERROR, score="", raw_response="[API-ERROR: RateLimitError]")
        canonical, counts = canonicalize_rows([error], expected)

        self.assertEqual([], canonical)
        self.assertEqual(1, counts["api_error"])

    def test_drops_rows_for_keys_outside_expected_set(self):
        expected: set[tuple[str, str, str]] = set()  # nothing expected
        rows = [sample_row()]
        canonical, counts = canonicalize_rows(rows, expected)

        self.assertEqual([], canonical)
        self.assertEqual(1, counts["stale_target"])

    def test_tie_break_is_independent_of_score(self):
        # Two genuine (non-error) answers to the same query -- must not
        # resolve toward whichever scored a hit, which would bias accuracy
        # upward. The FIRST row in file order wins regardless of score.
        expected = {("clock", "Timer", "baseline")}
        first_miss = sample_row(score=0, x_pred=999)
        second_hit = sample_row(score=1, x_pred=1)
        canonical, counts = canonicalize_rows([first_miss, second_hit], expected)

        self.assertEqual([first_miss], canonical)
        self.assertEqual(1, counts["duplicate"])


class FinalizeCsvTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.csv_path = Path(self.tmp.name) / "evaluation_results.csv"

    def test_reports_missing_key_and_does_not_rewrite(self):
        init_csv(self.csv_path)
        append_result(self.csv_path, sample_row())
        expected_order = [("clock", "Timer", "baseline"), ("clock", "Alarm", "baseline")]

        problems = finalize_csv(self.csv_path, expected_order)

        self.assertEqual(1, len(problems))
        self.assertIn("Alarm", problems[0])

    def test_reports_duplicate_key(self):
        init_csv(self.csv_path)
        append_result(self.csv_path, sample_row())
        append_result(self.csv_path, sample_row())
        expected_order = [("clock", "Timer", "baseline")]

        problems = finalize_csv(self.csv_path, expected_order)

        self.assertTrue(any("more than one" in p for p in problems))

    def test_reports_residual_api_error_row(self):
        init_csv(self.csv_path)
        append_result(self.csv_path, sample_row(status=STATUS_API_ERROR, score=""))
        expected_order = [("clock", "Timer", "baseline")]

        problems = finalize_csv(self.csv_path, expected_order)

        self.assertTrue(any("api_error" in p for p in problems))

    def test_clean_file_returns_no_problems_and_sorts_into_expected_order(self):
        init_csv(self.csv_path)
        append_result(self.csv_path, sample_row(target_text="Alarm", profile="elder_zoom_heavy"))
        append_result(self.csv_path, sample_row(target_text="Timer", profile="baseline"))
        expected_order = [
            ("clock", "Timer", "baseline"),
            ("clock", "Alarm", "elder_zoom_heavy"),
        ]

        problems = finalize_csv(self.csv_path, expected_order)

        self.assertEqual([], problems)
        with open(self.csv_path, "r", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(
            [("clock", "Timer", "baseline"), ("clock", "Alarm", "elder_zoom_heavy")],
            [(r["screen"], r["target_text"], r["profile"]) for r in rows],
        )

    def test_finalize_twice_is_a_no_op(self):
        # Reproducibility: canonicalizing an already-canonical file must not
        # change it further.
        init_csv(self.csv_path)
        append_result(self.csv_path, sample_row())
        expected_order = [("clock", "Timer", "baseline")]

        finalize_csv(self.csv_path, expected_order)
        with open(self.csv_path, "rb") as f:
            first_pass = f.read()
        finalize_csv(self.csv_path, expected_order)
        with open(self.csv_path, "rb") as f:
            second_pass = f.read()

        self.assertEqual(first_pass, second_pass)


class PrepareCsvCanonicalizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.csv_path = Path(self.tmp.name) / "evaluation_results.csv"

    def test_canonicalizes_and_backs_up_when_expected_keys_given(self):
        init_csv(self.csv_path)
        append_result(self.csv_path, sample_row())  # real
        append_result(self.csv_path, sample_row(status=STATUS_API_ERROR, score=""))  # stale dup

        completed = prepare_csv(
            self.csv_path, expected_keys={("clock", "Timer", "baseline")}
        )

        self.assertEqual({("clock", "Timer", "baseline")}, completed)
        with open(self.csv_path, "r", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(1, len(rows))
        self.assertEqual(STATUS_CO_PRESENT, rows[0]["status"])

        # The pre-canonicalization file is recoverable, with both rows intact.
        backups_made = list((self.csv_path.parent / BACKUP_DIR_NAME).glob("*.csv"))
        self.assertEqual(1, len(backups_made))
        with open(backups_made[0], "r", newline="", encoding="utf-8") as f:
            self.assertEqual(2, len(list(csv.DictReader(f))))

    def test_dropped_api_error_key_is_re_queried_by_returned_completed_set(self):
        # "Deleted rows must come back": a key whose only row was api_error
        # loses that row entirely, and must not appear in `completed`, so the
        # very next screen loop re-queries it.
        init_csv(self.csv_path)
        append_result(self.csv_path, sample_row(status=STATUS_API_ERROR, score=""))

        completed = prepare_csv(
            self.csv_path, expected_keys={("clock", "Timer", "baseline")}
        )

        self.assertNotIn(("clock", "Timer", "baseline"), completed)

    def test_no_expected_keys_leaves_old_unguarded_behaviour(self):
        init_csv(self.csv_path)
        append_result(self.csv_path, sample_row())
        append_result(self.csv_path, sample_row())  # duplicate, not canonicalized

        prepare_csv(self.csv_path)  # expected_keys omitted

        backup_path = self.csv_path.with_name(self.csv_path.name + ".bak")
        self.assertFalse(backup_path.is_file())
        with open(self.csv_path, "r", newline="", encoding="utf-8") as f:
            self.assertEqual(3, len(list(csv.reader(f))))  # header + 2 rows, untouched

    def test_canonicalizing_an_additive_schema_file_upgrades_its_header(self):
        # A file predating coord_space with expected_keys given (the repair
        # path canonicalize_results.py runs) must end up with the full
        # current header, not just be resumed with the old one forever.
        old_columns = CSV_COLUMNS[:-1]
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(old_columns)
            writer.writerow([
                "clock", "Timer", "baseline", STATUS_CO_PRESENT, "[1, 2]",
                "1", "2", "0", "0", "10", "10", "1", "1", "1", "bracket",
                PROMPT_MODE_VISION, "0",
            ])

        prepare_csv(self.csv_path, expected_keys={("clock", "Timer", "baseline")})

        with open(self.csv_path, "r", newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        self.assertEqual(CSV_COLUMNS, rows[0])
        self.assertEqual(2, len(rows))


if __name__ == "__main__":
    unittest.main()
