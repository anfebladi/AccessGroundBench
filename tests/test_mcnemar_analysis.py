import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from analysis.reports import comparison, grounding, reachability
from analysis.data import results as data, samples
from evaluation.storage import results


# Keep this broad historical regression suite readable while exercising the
# new responsibility-based modules rather than restoring a production facade.
mcnemar_analysis = SimpleNamespace(
    B2_LENGTH_CAP=samples.B2_LENGTH_CAP,
    PROMPT_MODE_VISION=results.PROMPT_MODE_VISION,
    STATUS_API_ERROR=results.STATUS_API_ERROR,
    STATUS_CO_PRESENT=results.STATUS_CO_PRESENT,
    build_clusters=grounding.build_clusters,
    compute_b2_targets=samples.compute_b2_targets,
    compute_contingency=grounding.compute_contingency,
    compute_reachability=reachability.compute_reachability,
    discover_result_csvs=data.discover_result_csvs,
    index_rows=data.index_rows,
    load_results=data.load_results,
    reclassify_label_changed=data.reclassify_label_changed,
    reclassify_off_frame=data.reclassify_off_frame,
    run_cross_comparison=comparison.run_cross_comparison,
    target_excluded_for_condition=samples.target_excluded_for_condition,
)


def touch_csv(path: Path) -> None:
    path.write_text("screen,target_text,profile\n", encoding="utf-8")


class IndexRowsTests(unittest.TestCase):
    def test_no_duplicates_indexes_normally(self):
        rows = [
            {"screen": "clock", "target_text": "Timer", "profile": "baseline",
             "status": mcnemar_analysis.STATUS_CO_PRESENT, "score": "1"},
        ]

        index = mcnemar_analysis.index_rows(rows)

        self.assertEqual(1, len(index))
        self.assertEqual("1", index[("clock", "Timer", "baseline")]["score"])

    def test_later_api_error_does_not_shadow_an_earlier_real_row(self):
        # The exact defect found in gpt-5.4_with_tree.csv: a real answer
        # followed by a stale api_error from a later resumed/retried run. A
        # naive last-write-wins dict comprehension would let the error hide
        # the real answer from every downstream co_present-gated table.
        real = {"screen": "gmail", "target_text": "1:51 PM", "profile": "elder_text_heavy",
                "status": mcnemar_analysis.STATUS_CO_PRESENT, "score": "1"}
        error = {"screen": "gmail", "target_text": "1:51 PM", "profile": "elder_text_heavy",
                 "status": mcnemar_analysis.STATUS_API_ERROR, "score": ""}

        index = mcnemar_analysis.index_rows([real, error])

        self.assertEqual(real, index[("gmail", "1:51 PM", "elder_text_heavy")])

    def test_earlier_api_error_is_replaced_by_a_later_real_row(self):
        error = {"screen": "gmail", "target_text": "1:51 PM", "profile": "elder_text_heavy",
                 "status": mcnemar_analysis.STATUS_API_ERROR, "score": ""}
        real = {"screen": "gmail", "target_text": "1:51 PM", "profile": "elder_text_heavy",
                "status": mcnemar_analysis.STATUS_CO_PRESENT, "score": "1"}

        index = mcnemar_analysis.index_rows([error, real])

        self.assertEqual(real, index[("gmail", "1:51 PM", "elder_text_heavy")])

    def test_duplicate_keys_trigger_a_warning(self):
        rows = [
            {"screen": "clock", "target_text": "Timer", "profile": "baseline",
             "status": mcnemar_analysis.STATUS_CO_PRESENT, "score": "1"},
            {"screen": "clock", "target_text": "Timer", "profile": "baseline",
             "status": mcnemar_analysis.STATUS_CO_PRESENT, "score": "0"},
        ]

        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            mcnemar_analysis.index_rows(rows)

        self.assertIn("duplicate", buf.getvalue().lower())


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


def make_row(status: str, **extra) -> dict:
    return {"status": status, **extra}


class ComputeReachabilityLabelChangedModeTests(unittest.TestCase):
    def setUp(self):
        self.index = {
            ("clock", "8:30 AM", "baseline"): make_row("co_present"),
            ("clock", "8:30 AM", "elder_text_heavy"): make_row("label_changed"),
            ("clock", "Mon-Fri", "baseline"): make_row("co_present"),
            ("clock", "Mon-Fri", "elder_text_heavy"): make_row("off_screen"),
            ("clock", "Alarm", "baseline"): make_row("co_present"),
            ("clock", "Alarm", "elder_text_heavy"): make_row("co_present"),
        }

    def test_exclude_mode_drops_label_changed_from_pool_entirely(self):
        present, total = mcnemar_analysis.compute_reachability(
            self.index, "elder_text_heavy", label_changed_mode="exclude"
        )
        self.assertEqual((1, 2), (present, total))

    def test_unreachable_mode_counts_label_changed_as_lost(self):
        # This is the pre-reclassification behaviour: label_changed rows
        # were indistinguishable from off_screen, so this mode must
        # reproduce the exact same numbers as before this feature existed.
        present, total = mcnemar_analysis.compute_reachability(
            self.index, "elder_text_heavy", label_changed_mode="unreachable"
        )
        self.assertEqual((1, 3), (present, total))

    def test_reachable_mode_counts_label_changed_as_present(self):
        present, total = mcnemar_analysis.compute_reachability(
            self.index, "elder_text_heavy", label_changed_mode="reachable"
        )
        self.assertEqual((2, 3), (present, total))

    def test_default_mode_matches_unreachable(self):
        default = mcnemar_analysis.compute_reachability(self.index, "elder_text_heavy")
        explicit = mcnemar_analysis.compute_reachability(
            self.index, "elder_text_heavy", label_changed_mode="unreachable"
        )
        self.assertEqual(explicit, default)

    def test_unknown_mode_raises(self):
        with self.assertRaises(ValueError):
            mcnemar_analysis.compute_reachability(
                self.index, "elder_text_heavy", label_changed_mode="bogus"
            )


class ReclassifyLabelChangedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.labels_dir = Path(self.tmp.name) / "labels"
        self.labels_dir.mkdir()

    def write_labels(self, screen: str, profile: str, records: list[dict]) -> None:
        (self.labels_dir / f"{screen}_{profile}.json").write_text(
            json.dumps(records), encoding="utf-8"
        )

    def test_relaxed_match_reclassifies_off_screen_to_label_changed(self):
        self.write_labels("clock", "elder_text_heavy", [
            {"text": "8:30 AM​͏͏", "box": [1, 2, 3, 4]},
        ])
        rows = [
            {"screen": "clock", "target_text": "8:30 AM",
             "profile": "elder_text_heavy", "status": "off_screen"},
        ]

        mcnemar_analysis.reclassify_label_changed(rows, self.labels_dir)

        self.assertEqual("label_changed", rows[0]["status"])
        self.assertIn("_label_changed_matched_text", rows[0])

    def test_genuinely_absent_target_stays_off_screen(self):
        self.write_labels("clock", "elder_text_heavy", [
            {"text": "Something else entirely", "box": [1, 2, 3, 4]},
        ])
        rows = [
            {"screen": "clock", "target_text": "8:30 AM",
             "profile": "elder_text_heavy", "status": "off_screen"},
        ]

        mcnemar_analysis.reclassify_label_changed(rows, self.labels_dir)

        self.assertEqual("off_screen", rows[0]["status"])

    def test_non_off_screen_rows_are_left_untouched(self):
        rows = [
            {"screen": "clock", "target_text": "8:30 AM",
             "profile": "baseline", "status": "co_present"},
        ]

        mcnemar_analysis.reclassify_label_changed(rows, self.labels_dir)

        self.assertEqual("co_present", rows[0]["status"])

    def test_missing_labels_directory_does_not_raise(self):
        rows = [
            {"screen": "clock", "target_text": "8:30 AM",
             "profile": "elder_text_heavy", "status": "off_screen"},
        ]

        result = mcnemar_analysis.reclassify_label_changed(
            rows, Path(self.tmp.name) / "does_not_exist"
        )

        self.assertEqual("off_screen", result[0]["status"])

    def test_missing_label_file_for_screen_profile_leaves_row_off_screen(self):
        rows = [
            {"screen": "unknown_screen", "target_text": "X",
             "profile": "elder_text_heavy", "status": "off_screen"},
        ]

        mcnemar_analysis.reclassify_label_changed(rows, self.labels_dir)

        self.assertEqual("off_screen", rows[0]["status"])


def write_png(path: Path, width: int, height: int) -> None:
    import struct
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
    )


class ReclassifyOffFrameTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.images_dir = Path(self.tmp.name) / "images"
        self.images_dir.mkdir()
        write_png(self.images_dir / "gmail_elder_text_heavy.png", 1080, 2219)

    def test_box_center_outside_image_is_reclassified_off_frame(self):
        rows = [{
            "screen": "gmail", "target_text": "Claude Team",
            "profile": "elder_text_heavy", "status": "co_present",
            "x_min": "180", "y_min": "2195", "x_max": "260", "y_max": "2266",
        }]

        mcnemar_analysis.reclassify_off_frame(rows, self.images_dir)

        self.assertEqual("off_frame", rows[0]["status"])

    def test_box_center_inside_image_is_left_co_present(self):
        rows = [{
            "screen": "gmail", "target_text": "Compose",
            "profile": "elder_text_heavy", "status": "co_present",
            "x_min": "100", "y_min": "100", "x_max": "200", "y_max": "200",
        }]

        mcnemar_analysis.reclassify_off_frame(rows, self.images_dir)

        self.assertEqual("co_present", rows[0]["status"])

    def test_label_changed_rows_are_also_checked(self):
        rows = [{
            "screen": "gmail", "target_text": "X",
            "profile": "elder_text_heavy", "status": "label_changed",
            "x_min": "180", "y_min": "2195", "x_max": "260", "y_max": "2266",
        }]

        mcnemar_analysis.reclassify_off_frame(rows, self.images_dir)

        self.assertEqual("off_frame", rows[0]["status"])

    def test_off_screen_rows_have_no_box_and_are_skipped(self):
        rows = [{
            "screen": "gmail", "target_text": "X",
            "profile": "elder_text_heavy", "status": "off_screen",
            "x_min": "", "y_min": "", "x_max": "", "y_max": "",
        }]

        mcnemar_analysis.reclassify_off_frame(rows, self.images_dir)

        self.assertEqual("off_screen", rows[0]["status"])

    def test_missing_image_leaves_row_unchanged(self):
        rows = [{
            "screen": "unknown", "target_text": "X",
            "profile": "elder_text_heavy", "status": "co_present",
            "x_min": "180", "y_min": "2195", "x_max": "260", "y_max": "2266",
        }]

        mcnemar_analysis.reclassify_off_frame(rows, self.images_dir)

        self.assertEqual("co_present", rows[0]["status"])

    def test_missing_images_directory_does_not_raise(self):
        rows = [{
            "screen": "gmail", "target_text": "Claude Team",
            "profile": "elder_text_heavy", "status": "co_present",
            "x_min": "180", "y_min": "2195", "x_max": "260", "y_max": "2266",
        }]

        result = mcnemar_analysis.reclassify_off_frame(
            rows, Path(self.tmp.name) / "does_not_exist"
        )

        self.assertEqual("co_present", result[0]["status"])

    def test_reachability_counts_off_frame_as_present(self):
        # The element genuinely exists on screen; only its scorability is
        # affected, so reachability (which never needs a score) must not
        # treat off_frame like off_screen.
        index = {
            ("gmail", "Claude Team", "baseline"): make_row("co_present"),
            ("gmail", "Claude Team", "elder_text_heavy"): make_row("off_frame"),
        }

        present, total = mcnemar_analysis.compute_reachability(
            index, "elder_text_heavy"
        )

        self.assertEqual((1, 1), (present, total))


def baseline_row(screen: str, text: str, box: list[int]) -> dict:
    return {
        "screen": screen, "target_text": text, "profile": "baseline",
        "status": "co_present",
        "x_min": str(box[0]), "y_min": str(box[1]),
        "x_max": str(box[2]), "y_max": str(box[3]),
    }


class ComputeB2TargetsTests(unittest.TestCase):
    def test_container_enclosing_another_target_is_excluded(self):
        rows = [
            baseline_row("gmail", "Container", [0, 0, 500, 500]),
            baseline_row("gmail", "Claude Team", [10, 10, 100, 100]),
        ]

        excluded = mcnemar_analysis.compute_b2_targets(rows)

        self.assertIn(("gmail", "Container"), excluded)
        self.assertNotIn(("gmail", "Claude Team"), excluded)

    def test_target_over_length_cap_is_excluded(self):
        long_text = "x" * (mcnemar_analysis.B2_LENGTH_CAP + 1)
        rows = [baseline_row("gmail", long_text, [0, 0, 10, 10])]

        excluded = mcnemar_analysis.compute_b2_targets(rows)

        self.assertIn(("gmail", long_text), excluded)

    def test_target_at_exactly_the_cap_is_not_excluded(self):
        exact_text = "x" * mcnemar_analysis.B2_LENGTH_CAP
        rows = [baseline_row("gmail", exact_text, [0, 0, 10, 10])]

        excluded = mcnemar_analysis.compute_b2_targets(rows)

        self.assertNotIn(("gmail", exact_text), excluded)

    def test_ordinary_non_overlapping_short_targets_are_not_excluded(self):
        rows = [
            baseline_row("clock", "Alarm", [0, 0, 50, 50]),
            baseline_row("clock", "Timer", [0, 60, 50, 110]),
        ]

        excluded = mcnemar_analysis.compute_b2_targets(rows)

        self.assertEqual(frozenset(), excluded)

    def test_containment_is_scoped_per_screen(self):
        # A box on one screen must not be compared against a box on another --
        # coordinates are only meaningful within the same capture.
        rows = [
            baseline_row("gmail", "A", [0, 0, 500, 500]),
            baseline_row("clock", "B", [10, 10, 100, 100]),
        ]

        excluded = mcnemar_analysis.compute_b2_targets(rows)

        self.assertEqual(frozenset(), excluded)

    def test_non_co_present_rows_are_skipped(self):
        row = baseline_row("gmail", "Ghost", [0, 0, 500, 500])
        row["status"] = "off_screen"
        rows = [row, baseline_row("gmail", "Claude Team", [10, 10, 100, 100])]

        excluded = mcnemar_analysis.compute_b2_targets(rows)

        self.assertEqual(frozenset(), excluded)


class TargetExcludedForConditionTests(unittest.TestCase):
    def test_full_sample_excludes_nothing(self):
        b2 = frozenset({("gmail", "Long text")})
        self.assertFalse(mcnemar_analysis.target_excluded_for_condition(
            "full", "settings_display", "X", "colorblind_deuteranomaly", b2
        ))
        self.assertFalse(mcnemar_analysis.target_excluded_for_condition(
            "full", "gmail", "Long text", "baseline", b2
        ))

    def test_b1_minimal_only_excludes_the_one_contaminated_cell(self):
        excl = mcnemar_analysis.target_excluded_for_condition
        self.assertTrue(excl("primary", "settings_display", "X",
                              "colorblind_deuteranomaly", frozenset()))
        # Same screen, different condition: not excluded -- font/density
        # losses on settings_display are ordinary scroll-off, not measured
        # contamination (see Stage B correction 2).
        self.assertFalse(excl("primary", "settings_display", "X",
                               "elder_text_heavy", frozenset()))

    def test_b2_applies_regardless_of_profile_including_baseline(self):
        b2 = frozenset({("gmail", "Long text")})
        excl = mcnemar_analysis.target_excluded_for_condition
        for profile in ("baseline", "elder_text_heavy", "colorblind_deuteranomaly"):
            self.assertTrue(excl("primary", "gmail", "Long text", profile, b2),
                             f"B2 must apply under {profile}")

    def test_b2_ignored_when_sample_does_not_use_it(self):
        b2 = frozenset({("gmail", "Long text")})
        self.assertFalse(mcnemar_analysis.target_excluded_for_condition(
            "full", "gmail", "Long text", "baseline", b2
        ))

    def test_precautionary_excludes_settings_accessibility_under_font_density(self):
        excl = mcnemar_analysis.target_excluded_for_condition
        self.assertTrue(excl("precautionary", "settings_accessibility", "X",
                              "elder_combo_max", frozenset()))
        self.assertFalse(excl("primary", "settings_accessibility", "X",
                               "elder_combo_max", frozenset()))

    def test_uniform_excludes_settings_accessibility_under_colour_too(self):
        excl = mcnemar_analysis.target_excluded_for_condition
        self.assertTrue(excl("uniform", "settings_accessibility", "X",
                              "colorblind_deuteranomaly", frozenset()))
        self.assertFalse(excl("precautionary", "settings_accessibility", "X",
                               "colorblind_deuteranomaly", frozenset()))

    def test_unknown_sample_raises(self):
        with self.assertRaises(ValueError):
            mcnemar_analysis.target_excluded_for_condition(
                "bogus", "clock", "X", "baseline", frozenset()
            )


class SampleExclusionIntegrationTests(unittest.TestCase):
    """compute_reachability / build_clusters / compute_contingency honoring sample."""

    def setUp(self):
        # settings_display has two targets, one of which is contaminated
        # under colorblind_deuteranomaly (present in baseline, "off_screen"
        # under colorblind due to the banner) and clean under text_heavy.
        self.index = {
            ("settings_display", "Brightness", "baseline"): make_row("co_present", score="1"),
            ("settings_display", "Brightness", "colorblind_deuteranomaly"):
                make_row("co_present", score="1"),
            ("settings_display", "Brightness", "elder_text_heavy"):
                make_row("co_present", score="1"),
            ("settings_display", "Color", "baseline"): make_row("co_present", score="1"),
            ("settings_display", "Color", "colorblind_deuteranomaly"):
                make_row("off_screen"),
            ("settings_display", "Color", "elder_text_heavy"): make_row("co_present", score="1"),
        }

    def test_full_sample_colour_reachability_is_contaminated(self):
        present, total = mcnemar_analysis.compute_reachability(
            self.index, "colorblind_deuteranomaly", sample="full"
        )
        self.assertEqual((1, 2), (present, total))

    def test_primary_sample_colour_reachability_is_100_percent(self):
        # This is the correctness check from the plan: with the contaminated
        # cell excluded, colour reachability must read exactly 100% -- the
        # value a software-only transform has to produce by construction.
        present, total = mcnemar_analysis.compute_reachability(
            self.index, "colorblind_deuteranomaly", sample="primary"
        )
        self.assertEqual((0, 0), (present, total))  # pool emptied: both targets removed

    def test_primary_sample_does_not_affect_other_conditions(self):
        # elder_text_heavy is not in B1's exclusion set for settings_display,
        # so its pool must be untouched.
        present, total = mcnemar_analysis.compute_reachability(
            self.index, "elder_text_heavy", sample="primary"
        )
        self.assertEqual((2, 2), (present, total))

    def test_build_clusters_excludes_contaminated_condition_only(self):
        indices = {"model-a": self.index}
        clusters_colour = mcnemar_analysis.build_clusters(
            indices, "colorblind_deuteranomaly", sample="primary"
        )
        clusters_text = mcnemar_analysis.build_clusters(
            indices, "elder_text_heavy", sample="primary"
        )
        self.assertEqual({}, clusters_colour)
        self.assertEqual(2, len(clusters_text))

    def test_compute_contingency_excludes_contaminated_condition_only(self):
        a, b, c, d = mcnemar_analysis.compute_contingency(
            self.index, "colorblind_deuteranomaly", sample="primary"
        )
        self.assertEqual((0, 0, 0, 0), (a, b, c, d))

        a, b, c, d = mcnemar_analysis.compute_contingency(
            self.index, "elder_text_heavy", sample="primary"
        )
        self.assertEqual(2, a + b + c + d)


CROSS_HEADER = (
    "screen,target_text,profile,status,raw_response,x_pred,y_pred,"
    "x_min,y_min,x_max,y_max,score,trials,trial_scores,parse_method,"
    "prompt_mode,tree_rows_sent\n"
)


class RunCrossComparisonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def write_csv(self, name: str, rows: list[str]) -> Path:
        path = self.dir / name
        path.write_text(CROSS_HEADER + "".join(rows), encoding="utf-8")
        return path

    def read_out(self) -> list[dict]:
        out = next(self.dir.glob("mcnemar_compare_*.csv"))
        import csv as _csv
        with open(out, encoding="utf-8") as f:
            return list(_csv.DictReader(f))

    def test_output_carries_a_sample_column(self):
        row = ("clock,Alarm,elder_text_heavy,co_present,\"[1, 2]\",1,2,"
               "0,0,10,10,1,1,1,bracket,vision,0\n")
        base = ("clock,Alarm,baseline,co_present,\"[1, 2]\",1,2,"
                "0,0,10,10,1,1,1,bracket,vision,0\n")
        a = self.write_csv("evaluation_results_m.csv", [base, row])
        b = self.write_csv("evaluation_results_m_with_tree.csv", [base, row])

        mcnemar_analysis.run_cross_comparison(a, b, ["elder_text_heavy"])

        out = self.read_out()
        self.assertEqual("primary", out[0]["Sample"])

    def test_identical_files_produce_no_discordant_pairs(self):
        # Parity check: a file compared against itself cannot disagree, so
        # every profile must read b=0 c=0. Any nonzero value means the
        # pairing logic is mismatching rows.
        base = ("clock,Alarm,baseline,co_present,\"[1, 2]\",1,2,"
                "0,0,10,10,1,1,1,bracket,vision,0\n")
        exp = ("clock,Alarm,elder_text_heavy,co_present,\"[1, 2]\",1,2,"
               "0,0,10,10,1,1,1,bracket,vision,0\n")
        a = self.write_csv("evaluation_results_m.csv", [base, exp])
        b = self.write_csv("evaluation_results_m_with_tree.csv", [base, exp])

        mcnemar_analysis.run_cross_comparison(a, b, ["elder_text_heavy"])

        out = self.read_out()
        self.assertEqual("0", out[0]["Tree_Hurt_b"])
        self.assertEqual("0", out[0]["Tree_Helped_c"])

    def test_b2_excluded_target_is_dropped_from_the_comparison(self):
        long_text = "x" * (mcnemar_analysis.B2_LENGTH_CAP + 1)
        base_keep = ("gmail,Short,baseline,co_present,\"[1, 2]\",1,2,"
                     "0,0,10,10,1,1,1,bracket,vision,0\n")
        exp_keep = ("gmail,Short,elder_text_heavy,co_present,\"[1, 2]\",1,2,"
                    "0,0,10,10,1,1,1,bracket,vision,0\n")
        base_drop = (f"gmail,{long_text},baseline,co_present,\"[1, 2]\",1,2,"
                     "0,0,10,10,1,1,1,bracket,vision,0\n")
        exp_drop = (f"gmail,{long_text},elder_text_heavy,co_present,\"[1, 2]\",1,2,"
                    "0,0,10,10,1,1,1,bracket,vision,0\n")
        rows = [base_keep, exp_keep, base_drop, exp_drop]
        a = self.write_csv("evaluation_results_m.csv", rows)
        b = self.write_csv("evaluation_results_m_with_tree.csv", rows)

        mcnemar_analysis.run_cross_comparison(a, b, ["elder_text_heavy"], sample="primary")
        primary_pairs = int(self.read_out()[0]["Total_Pairs"])

        mcnemar_analysis.run_cross_comparison(a, b, ["elder_text_heavy"], sample="full")
        full_pairs = int(self.read_out()[0]["Total_Pairs"])

        self.assertEqual(1, primary_pairs, "B2 target must be excluded under primary")
        self.assertEqual(2, full_pairs, "full sample must keep both targets")

    def test_b1_contaminated_cell_is_dropped_under_primary(self):
        base = ("settings_display,Color,baseline,co_present,\"[1, 2]\",1,2,"
                "0,0,10,10,1,1,1,bracket,vision,0\n")
        exp = ("settings_display,Color,colorblind_deuteranomaly,co_present,\"[1, 2]\",1,2,"
               "0,0,10,10,1,1,1,bracket,vision,0\n")
        a = self.write_csv("evaluation_results_m.csv", [base, exp])
        b = self.write_csv("evaluation_results_m_with_tree.csv", [base, exp])

        mcnemar_analysis.run_cross_comparison(
            a, b, ["colorblind_deuteranomaly"], sample="primary"
        )

        self.assertEqual("0", self.read_out()[0]["Total_Pairs"])


if __name__ == "__main__":
    unittest.main()
