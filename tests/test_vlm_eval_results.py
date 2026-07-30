import csv
import tempfile
import unittest
from pathlib import Path

from vlm_eval.results import (
    CSV_COLUMNS,
    STATUS_API_ERROR,
    STATUS_CO_PRESENT,
    append_result,
    init_csv,
    load_completed_keys,
    prepare_csv,
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
             "0", "0", "10", "10", "1", "1", "1", "bracket"],
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


if __name__ == "__main__":
    unittest.main()
