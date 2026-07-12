import unittest

from vlm_eval.scoring import hit_test, parse_coordinates


class VlmEvalScoringTests(unittest.TestCase):
    def test_parse_coordinates_extracts_first_integer_pair(self):
        self.assertEqual((123, 456), parse_coordinates("[123, 456]"))
        self.assertEqual((12, 34), parse_coordinates("click at 12,34 please"))

    def test_parse_coordinates_preserves_negative_values(self):
        self.assertEqual((-5, 34), parse_coordinates("[-5, 34]"))

    def test_parse_coordinates_returns_negative_sentinel_on_failure(self):
        self.assertEqual((-1, -1), parse_coordinates("no coordinate here"))

    def test_hit_test_scores_inside_and_edge_points(self):
        box = [10, 20, 30, 40]

        self.assertEqual(1, hit_test(20, 30, box))
        self.assertEqual(1, hit_test(10, 20, box))
        self.assertEqual(1, hit_test(30, 40, box))

    def test_hit_test_rejects_outside_points(self):
        box = [10, 20, 30, 40]

        self.assertEqual(0, hit_test(9, 30, box))
        self.assertEqual(0, hit_test(20, 41, box))


if __name__ == "__main__":
    unittest.main()
