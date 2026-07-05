import csv
import tempfile
import unittest
from pathlib import Path

from vlm_eval.results import CSV_COLUMNS, append_result, init_csv


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
            append_result(csv_path, {
                "screen": "clock",
                "target_text": "Timer",
                "profile": "baseline",
                "raw_response": "[1, 2]",
                "x_pred": 1,
                "y_pred": 2,
                "x_min": 0,
                "y_min": 0,
                "x_max": 10,
                "y_max": 10,
                "score": 1,
            })

            with open(csv_path, "r", encoding="utf-8", newline="") as f:
                rows = list(csv.reader(f))

        self.assertEqual(CSV_COLUMNS, rows[0])
        self.assertEqual(
            ["clock", "Timer", "baseline", "[1, 2]", "1", "2",
             "0", "0", "10", "10", "1"],
            rows[1],
        )


if __name__ == "__main__":
    unittest.main()
