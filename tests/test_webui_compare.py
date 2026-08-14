"""Fixture-based statistics test for webui.backend.services.compare.compare_model.

Not a smoke test: every assertion here is checked against a hand-derived
expected value (exact binomial p-values computed independently via
math.comb, Holm thresholds computed from the documented alpha/(m-i)
formula), the same standard the rest of the pipeline's statistics are held to.

The star test (`test_holm_correction_scopes_to_full_family`) is the direct
regression check for the family-scoping defect the Compare endpoint's design
had to avoid: correcting Holm-Bonferroni across only the requested model's
own profiles, rather than every model discovered for the dataset, can make
the same p-value significant in one context and not the other. The fixture
is built so model_a's own McNemar p-value (0.0390625) sits *between* the
two possible thresholds (0.025 with a 2-model family, 0.05 with a 1-model
family) -- so if the endpoint ever regresses to correcting per-model instead
of per-dataset, `significant` flips and this test catches it.
"""
import csv
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import paths
from evaluation.storage.results import CSV_COLUMNS
from webui.backend.services.compare import CompareError, compare_model

SCREEN = "clock"
PROFILE = "elder_text_heavy"


def _row(target_text: str, profile: str, score: str) -> dict:
    row = {col: "" for col in CSV_COLUMNS}
    row.update({
        "screen": SCREEN,
        "target_text": target_text,
        "profile": profile,
        "status": "co_present",
        "score": score,
        "prompt_mode": "vision",
    })
    return row


def _write_model_csv(path: Path, pairs: list[tuple[str, str]]) -> None:
    """pairs: list of (baseline_score, profile_score) for one target each."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, (base_score, prof_score) in enumerate(pairs):
        target = f"t{i}"
        rows.append(_row(target, "baseline", base_score))
        rows.append(_row(target, PROFILE, prof_score))
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


# model_a: a=8 (1,1), b=8 (1,0), c=1 (0,1), d=3 (0,0) -- total 20.
# base_acc = (8+8)/20 = 80%; exact McNemar p for b=8,c=1 is 0.0390625.
MODEL_A_PAIRS = (
    [("1", "1")] * 8 + [("1", "0")] * 8 + [("0", "1")] * 1 + [("0", "0")] * 3
)
# model_b: a=15 (1,1), b=2 (1,0), c=2 (0,1), d=1 (0,0) -- total 20.
# base_acc = (15+2)/20 = 85%; exact McNemar p for b=2,c=2 is 1.0.
MODEL_B_PAIRS = (
    [("1", "1")] * 15 + [("1", "0")] * 2 + [("0", "1")] * 2 + [("0", "0")] * 1
)


class CompareModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.addCleanup(self.tmp_dir.cleanup)
        self.dataset_dir = self.root / "mydataset"
        self.patcher = mock.patch.object(paths, "PROJECT_ROOT", self.root)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        evaluations = paths.evaluations_dir(self.dataset_dir)
        _write_model_csv(evaluations / "model_a_vision.csv", MODEL_A_PAIRS)
        _write_model_csv(evaluations / "model_b_vision.csv", MODEL_B_PAIRS)

    def test_unknown_model_raises_compare_error(self):
        with self.assertRaises(CompareError):
            compare_model(self.dataset_dir, "no_such_model", mode="vision", sample="full")

    def test_no_result_files_raises_compare_error(self):
        with self.assertRaises(CompareError):
            compare_model(self.dataset_dir, "model_a", mode="tree", sample="full")

    def test_accuracy_and_discordant_counts_match_the_fixture(self):
        result = compare_model(self.dataset_dir, "model_a", mode="vision", sample="full")
        row = next(p for p in result["profiles"] if p["profile"] == PROFILE)

        self.assertAlmostEqual(80.0, row["baseline_accuracy"])
        self.assertAlmostEqual(45.0, row["profile_accuracy"])  # (a+c)/total = 9/20
        self.assertEqual(8, row["b"])
        self.assertEqual(1, row["c"])
        self.assertEqual(20, row["total"])
        self.assertAlmostEqual(0.0390625, row["p_value"], places=7)
        self.assertEqual("", row["power_flag"])  # 80% is between floor (50%) and ceiling (95%)

    def test_reachability_is_present_for_every_profile(self):
        result = compare_model(self.dataset_dir, "model_a", mode="vision", sample="full")
        row = next(p for p in result["profiles"] if p["profile"] == PROFILE)
        self.assertIsNotNone(row["reachability"])
        self.assertGreaterEqual(row["reachability"], 0.0)
        self.assertLessEqual(row["reachability"], 1.0)

    def test_holm_correction_scopes_to_full_family(self):
        """The star test: significance for model_a must depend on the whole
        dataset's model roster, not on which model was requested."""
        both_models = compare_model(self.dataset_dir, "model_a", mode="vision", sample="full")
        row_both = next(p for p in both_models["profiles"] if p["profile"] == PROFILE)

        self.assertEqual(["model_a", "model_b"], both_models["models_in_family"])
        self.assertAlmostEqual(0.025, row_both["holm_threshold"], places=10)  # alpha/(2-0)
        self.assertFalse(row_both["significant"])  # 0.0390625 >= 0.025
        self.assertEqual("", row_both["power_flag"])  # 80% baseline is neither ceiling nor floor
        self.assertEqual("no_change", row_both["significance_state"])

        # Remove model_b's file: the family shrinks to one model, and the
        # SAME p-value (0.0390625) now falls under a looser threshold
        # (alpha/1 = 0.05) and becomes significant. If the endpoint ever
        # corrects per-model instead of per-dataset, this assertion pair is
        # what would go from "different" to "identical" and expose it.
        (paths.evaluations_dir(self.dataset_dir) / "model_b_vision.csv").unlink()
        one_model = compare_model(self.dataset_dir, "model_a", mode="vision", sample="full")
        row_one = next(p for p in one_model["profiles"] if p["profile"] == PROFILE)

        self.assertEqual(["model_a"], one_model["models_in_family"])
        self.assertAlmostEqual(0.05, row_one["holm_threshold"], places=10)  # alpha/(1-0)
        self.assertTrue(row_one["significant"])  # 0.0390625 < 0.05
        self.assertEqual("significant", row_one["significance_state"])

        # The two runs must disagree on the SAME underlying p-value -- that
        # disagreement, driven only by family size, is the whole point.
        self.assertEqual(row_both["p_value"], row_one["p_value"])
        self.assertNotEqual(row_both["significant"], row_one["significant"])


if __name__ == "__main__":
    unittest.main()
