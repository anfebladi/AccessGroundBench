import csv
import unittest
from pathlib import Path

from mcnemar.pairing import (
    build_cross_file_pairs,
    build_pairs,
    compute_contingency,
    compute_cross_contingency,
)
from mcnemar.reporting import (
    cross_csv_header,
    cross_csv_row,
    format_cross_report,
    format_report,
    standard_csv_header,
    standard_csv_row,
)
from mcnemar.service import AnalysisRecord, analyze_profiles
from mcnemar.statistics import run_mcnemar


class McNemarPairingTests(unittest.TestCase):
    def test_single_file_pairing_and_contingency_preserve_legacy_skips(self):
        rows = [
            {"screen": "clock", "target_text": "Alarm", "profile": "baseline", "score": "1"},
            {"screen": "clock", "target_text": "Alarm", "profile": "elder_text_heavy", "score": "0"},
            {"screen": "clock", "target_text": "Timer", "profile": "baseline", "score": "0"},
            {"screen": "clock", "target_text": "Timer", "profile": "elder_text_heavy", "score": "1"},
            {"screen": "clock", "target_text": "Stopwatch", "profile": "baseline", "score": "1"},
        ]

        pairs = build_pairs(rows)

        self.assertEqual({"baseline": 1, "elder_text_heavy": 0}, pairs["clock_Alarm"])
        self.assertEqual((0, 1, 1, 0), compute_contingency(pairs, "elder_text_heavy"))

    def test_cross_file_pairing_and_contingency_skip_unpaired_rows(self):
        rows_a = [
            {"screen": "clock", "target_text": "Alarm", "profile": "baseline", "score": "1"},
            {"screen": "clock", "target_text": "Timer", "profile": "baseline", "score": "0"},
            {"screen": "clock", "target_text": "Stopwatch", "profile": "baseline", "score": "1"},
        ]
        rows_b = [
            {"screen": "clock", "target_text": "Alarm", "profile": "baseline", "score": "0"},
            {"screen": "clock", "target_text": "Timer", "profile": "baseline", "score": "1"},
            {"screen": "clock", "target_text": "Lap", "profile": "baseline", "score": "1"},
        ]

        pairs = build_cross_file_pairs(rows_a, rows_b)

        self.assertEqual({"baseline": (1, 0)}, pairs["clock_Alarm"])
        self.assertEqual((0, 1, 1, 0), compute_cross_contingency(pairs, "baseline"))


class McNemarStatisticsTests(unittest.TestCase):
    def test_test_selection_changes_at_existing_threshold(self):
        exact = run_mcnemar(12, 12)
        asymptotic = run_mcnemar(13, 12)

        self.assertEqual("Exact Binomial (n=24)", exact["test"])
        self.assertIsNone(exact["statistic"])
        self.assertEqual("Asymptotic (Edwards' correction, n=25)", asymptotic["test"])
        self.assertEqual(0.0, asymptotic["statistic"])
        self.assertAlmostEqual(1.0, asymptotic["p_value"])


class McNemarReportingTests(unittest.TestCase):
    def test_standard_records_drive_report_and_csv_row(self):
        record = AnalysisRecord(
            "elder_text_heavy", 1, 1, 0, 0, run_mcnemar(1, 0)
        )

        report = format_report(record)

        self.assertIn("Profile: elder_text_heavy  vs.  baseline", report)
        self.assertIn("Baseline Accuracy:     100.0% (2/2)", report)
        self.assertIn("Experimental Accuracy: 50.0% (1/2)", report)
        self.assertEqual(
            [
                "Profile", "Total_Pairs", "Both_Pass_a", "Broke_It_b",
                "Fluke_Recovery_c", "Both_Fail_d", "Discordant_Pairs",
                "Baseline_Acc", "Exp_Acc", "Test_Used", "Statistic", "P_Value",
                "Significant", "Floor_Limited",
            ],
            standard_csv_header(),
        )
        self.assertEqual(
            ["elder_text_heavy", 2, 1, 1, 0, 0, 1, "100.0%", "50.0%",
             "Exact Binomial (n=1)", "", 1.0, "No", "No"],
            standard_csv_row(record),
        )

    def test_cross_records_drive_report_and_csv_row(self):
        record = AnalysisRecord("baseline", 1, 0, 1, 0, run_mcnemar(0, 1))

        report = format_cross_report(record)

        self.assertIn("Vision-only vs. Vision + A11y Tree", report)
        self.assertIn("Vision-only Accuracy:  50.0% (1/2)", report)
        self.assertIn("With Tree Accuracy:    100.0% (2/2)", report)
        self.assertEqual("VisionOnly_Acc", cross_csv_header()[7])
        self.assertEqual(
            ["baseline", 2, 1, 0, 1, 0, 1, "50.0%", "100.0%",
             "Exact Binomial (n=1)", "", 1.0, "No"],
            cross_csv_row(record),
        )


class McNemarCharacterizationTests(unittest.TestCase):
    def test_representative_committed_results_remain_unchanged(self):
        csv_path = Path("dataset/evaluation_results_9router_cx_gpt-5.4.csv")
        with csv_path.open(newline="", encoding="utf-8") as handle:
            pairs = build_pairs(list(csv.DictReader(handle)))

        profiles = [
            "elder_text_heavy",
            "elder_zoom_heavy",
            "elder_combo_max",
            "elder_combo_rtl",
            "colorblind_deuteranomaly",
        ]
        records = analyze_profiles(pairs, profiles, compute_contingency)
        observed = {
            record.profile: (record.a, record.b, record.c, record.d, record.result["test"])
            for record in records
        }

        self.assertEqual(
            {
                "elder_text_heavy": (61, 23, 7, 74, "Asymptotic (Edwards' correction, n=30)"),
                "elder_zoom_heavy": (70, 16, 27, 55, "Asymptotic (Edwards' correction, n=43)"),
                "elder_combo_max": (61, 25, 17, 65, "Asymptotic (Edwards' correction, n=42)"),
                "elder_combo_rtl": (63, 23, 17, 65, "Asymptotic (Edwards' correction, n=40)"),
                "colorblind_deuteranomaly": (78, 8, 15, 67, "Exact Binomial (n=23)"),
            },
            observed,
        )
        self.assertAlmostEqual(0.0061698993205441255, records[0].result["p_value"])
        self.assertAlmostEqual(0.21003961563110352, records[-1].result["p_value"])


if __name__ == "__main__":
    unittest.main()
