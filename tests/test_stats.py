import unittest

from analysis.stats import (
    cluster_permutation_test,
    conditional_odds_ratio,
    exact_binomial_two_tailed,
    holm_bonferroni,
    mcnemar_test,
    paired_difference_interval,
    sign_test,
    wilson_interval,
)


class WilsonIntervalTests(unittest.TestCase):
    def test_interval_brackets_the_point_estimate(self):
        low, high = wilson_interval(50, 100)
        self.assertLess(low, 0.5)
        self.assertGreater(high, 0.5)

    def test_interval_stays_inside_unit_range_at_the_boundary(self):
        # The Wald interval would run past 1.0 here; Wilson must not.
        low, high = wilson_interval(100, 100)
        self.assertGreaterEqual(low, 0.0)
        self.assertLessEqual(high, 1.0)
        self.assertLess(low, 1.0)

    def test_empty_sample_returns_zero_width(self):
        self.assertEqual((0.0, 0.0), wilson_interval(0, 0))


class PairedDifferenceTests(unittest.TestCase):
    def test_difference_matches_arm_accuracies(self):
        diff, low, high = paired_difference_interval(a=80, b=15, c=5, d=0)
        self.assertAlmostEqual(0.10, diff, places=6)
        self.assertLess(low, diff)
        self.assertGreater(high, diff)

    def test_no_difference_interval_contains_zero(self):
        diff, low, high = paired_difference_interval(a=90, b=5, c=5, d=0)
        self.assertAlmostEqual(0.0, diff, places=6)
        self.assertLessEqual(low, 0.0)
        self.assertGreaterEqual(high, 0.0)


class McNemarTests(unittest.TestCase):
    def test_no_discordant_pairs_is_not_significant(self):
        result = mcnemar_test(0, 0)
        self.assertEqual(1.0, result["p_value"])

    def test_small_samples_use_the_exact_test(self):
        self.assertIn("Exact Binomial", mcnemar_test(6, 0)["test"])

    def test_large_samples_use_the_asymptotic_test(self):
        self.assertIn("Asymptotic", mcnemar_test(40, 5)["test"])

    def test_exact_binomial_matches_hand_computed_value(self):
        # b=6, c=0 -> 2 * 0.5**6
        self.assertAlmostEqual(0.03125, exact_binomial_two_tailed(6, 0), places=10)

    def test_lopsided_split_is_significant(self):
        self.assertLess(mcnemar_test(20, 2)["p_value"], 0.05)

    def test_even_split_is_not_significant(self):
        self.assertGreater(mcnemar_test(15, 15)["p_value"], 0.05)


class OddsRatioTests(unittest.TestCase):
    def test_point_estimate_is_the_discordant_ratio(self):
        point, low, high = conditional_odds_ratio(20, 10)
        self.assertAlmostEqual(2.0, point)
        self.assertLess(low, 2.0)
        self.assertGreater(high, 2.0)

    def test_zero_recoveries_gives_an_infinite_point_estimate(self):
        point, low, _ = conditional_odds_ratio(6, 0)
        self.assertEqual(float("inf"), point)
        self.assertGreater(low, 0.0)

    def test_undefined_without_discordant_pairs(self):
        self.assertEqual((None, None, None), conditional_odds_ratio(0, 0))


class HolmBonferroniTests(unittest.TestCase):
    def test_thresholds_step_down_with_rank(self):
        results = holm_bonferroni({"a": 0.001, "b": 0.02, "c": 0.04})
        self.assertAlmostEqual(0.05 / 3, results["a"].threshold)
        self.assertAlmostEqual(0.05 / 2, results["b"].threshold)
        self.assertAlmostEqual(0.05 / 1, results["c"].threshold)

    def test_only_tests_below_their_threshold_are_rejected(self):
        # a clears 0.05/2; b does not clear 0.05/1.
        results = holm_bonferroni({"a": 0.001, "b": 0.06})
        self.assertTrue(results["a"].reject)
        self.assertFalse(results["b"].reject)

    def test_procedure_stops_at_the_first_failure(self):
        # Smallest p (0.03) fails against 0.05/3, so the step-down halts and
        # 0.045 is retained even though it would clear 0.05/1 in isolation.
        results = holm_bonferroni({"a": 0.03, "b": 0.04, "c": 0.045})
        self.assertFalse(results["a"].reject)
        self.assertFalse(results["b"].reject)
        self.assertFalse(results["c"].reject)
        self.assertAlmostEqual(0.05, results["c"].threshold)

    def test_a_single_test_is_uncorrected(self):
        results = holm_bonferroni({"only": 0.04})
        self.assertAlmostEqual(0.05, results["only"].threshold)
        self.assertTrue(results["only"].reject)


class ClusterPermutationTests(unittest.TestCase):
    def test_planted_effect_is_detected(self):
        # 40 targets that always degrade, 2 that recover: unmistakable.
        clusters = {f"t{i}": [(1, 0)] for i in range(40)}
        clusters.update({f"r{i}": [(0, 1)] for i in range(2)})

        result = cluster_permutation_test(clusters, n_permutations=2000, seed=1)

        self.assertEqual(40, result["b"])
        self.assertEqual(2, result["c"])
        self.assertLess(result["p_value"], 0.01)

    def test_no_effect_is_not_significant(self):
        clusters = {f"d{i}": [(1, 0)] for i in range(20)}
        clusters.update({f"u{i}": [(0, 1)] for i in range(20)})

        result = cluster_permutation_test(clusters, n_permutations=2000, seed=1)

        self.assertGreater(result["p_value"], 0.05)

    def test_concordant_pairs_alone_yield_no_evidence(self):
        clusters = {f"t{i}": [(1, 1)] for i in range(50)}

        result = cluster_permutation_test(clusters, n_permutations=1000, seed=1)

        self.assertEqual(0, result["b"])
        self.assertEqual(0, result["c"])
        self.assertEqual(1.0, result["p_value"])

    def test_clustering_is_more_conservative_than_treating_rows_as_independent(self):
        # The same 10 targets measured under 7 models. Clustered, this is 10
        # independent units, not 70 -- so the p-value must be materially larger
        # than the unclustered version of identical data.
        clustered = {f"t{i}": [(1, 0)] * 7 for i in range(10)}
        unclustered = {f"t{i}-{m}": [(1, 0)] for i in range(10) for m in range(7)}

        p_clustered = cluster_permutation_test(clustered, 5000, seed=2)["p_value"]
        p_unclustered = cluster_permutation_test(unclustered, 5000, seed=2)["p_value"]

        self.assertGreater(p_clustered, p_unclustered)

    def test_empty_input_is_handled(self):
        result = cluster_permutation_test({}, n_permutations=100, seed=0)
        self.assertEqual(1.0, result["p_value"])
        self.assertEqual(0, result["n_clusters"])

    def test_seed_makes_results_reproducible(self):
        clusters = {f"t{i}": [(1, 0)] for i in range(12)}
        first = cluster_permutation_test(clusters, 1000, seed=7)["p_value"]
        second = cluster_permutation_test(clusters, 1000, seed=7)["p_value"]
        self.assertEqual(first, second)


class SignTestTests(unittest.TestCase):
    def test_unanimous_direction_across_seven_models(self):
        # The elder_text_heavy pattern: 7/7 down -> 2 * 0.5**7.
        self.assertAlmostEqual(0.015625, sign_test(7, 0), places=10)

    def test_even_split_is_not_significant(self):
        self.assertEqual(1.0, sign_test(3, 3))

    def test_all_ties_returns_one(self):
        self.assertEqual(1.0, sign_test(0, 0))


if __name__ == "__main__":
    unittest.main()
