import tempfile
import unittest
from pathlib import Path

import mcnemar_analysis


def touch_csv(path: Path) -> None:
    path.write_text("screen,target_text,profile\n", encoding="utf-8")


class DiscoverResultCsvsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data_dir = Path(self.tmp.name)

    def test_default_mode_excludes_with_tree_files(self):
        touch_csv(self.data_dir / "evaluation_results_gpt-5.5.csv")
        touch_csv(self.data_dir / "evaluation_results_local_ferret-ui-llama8b.csv")
        touch_csv(self.data_dir / "evaluation_results_local_ferret-ui-llama8b_with_tree.csv")

        found = mcnemar_analysis.discover_result_csvs(self.data_dir, "vision")

        names = sorted(p.name for p in found)
        self.assertEqual(
            ["evaluation_results_gpt-5.5.csv",
             "evaluation_results_local_ferret-ui-llama8b.csv"],
            names,
        )

    def test_tree_mode_selects_only_with_tree_files(self):
        touch_csv(self.data_dir / "evaluation_results_gpt-5.5.csv")
        touch_csv(self.data_dir / "evaluation_results_local_ferret-ui-llama8b_with_tree.csv")

        found = mcnemar_analysis.discover_result_csvs(self.data_dir, "tree")

        names = [p.name for p in found]
        self.assertEqual(
            ["evaluation_results_local_ferret-ui-llama8b_with_tree.csv"], names
        )

    def test_no_matching_files_returns_empty_list(self):
        touch_csv(self.data_dir / "evaluation_results_gpt-5.5.csv")

        found = mcnemar_analysis.discover_result_csvs(self.data_dir, "tree")

        self.assertEqual([], found)


class LoadResultsPromptModeDefaultTests(unittest.TestCase):
    def test_missing_prompt_mode_columns_default_to_vision_and_zero(self):
        # The archived experiment_2 CSVs predate the prompt_mode/tree_rows_sent
        # columns entirely; load_results must not choke on their absence, and
        # must default them consistently with what was actually run (vision).
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "evaluation_results_old-model.csv"
            csv_path.write_text(
                "screen,target_text,profile,status,raw_response,x_pred,y_pred,"
                "x_min,y_min,x_max,y_max,score,trials,trial_scores,parse_method\n"
                "clock,8:30 AM,baseline,co_present,\"[1, 2]\",1,2,0,0,10,10,1,1,1,bracket\n",
                encoding="utf-8",
            )

            rows = mcnemar_analysis.load_results(csv_path)

        self.assertEqual(1, len(rows))
        self.assertEqual(mcnemar_analysis.PROMPT_MODE_VISION, rows[0]["prompt_mode"])
        self.assertEqual("0", rows[0]["tree_rows_sent"])

    def test_present_prompt_mode_column_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "evaluation_results_new-model_with_tree.csv"
            csv_path.write_text(
                "screen,target_text,profile,status,raw_response,x_pred,y_pred,"
                "x_min,y_min,x_max,y_max,score,trials,trial_scores,parse_method,"
                "prompt_mode,tree_rows_sent\n"
                "clock,8:30 AM,baseline,co_present,\"[1, 2]\",1,2,0,0,10,10,1,1,1,"
                "bracket,tree,5\n",
                encoding="utf-8",
            )

            rows = mcnemar_analysis.load_results(csv_path)

        self.assertEqual("tree", rows[0]["prompt_mode"])
        self.assertEqual("5", rows[0]["tree_rows_sent"])


if __name__ == "__main__":
    unittest.main()
