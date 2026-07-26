import unittest

from vlm_eval.scoring import hit_test, parse_coordinates


class VlmEvalScoringTests(unittest.TestCase):
    def test_parse_coordinates_accepts_json_array(self):
        self.assertEqual((123, 456), parse_coordinates("[123, 456]"))
        self.assertEqual((12.5, 34), parse_coordinates("[12.5, 34]"))

    def test_parse_coordinates_preserves_negative_values(self):
        self.assertEqual((-5, 34), parse_coordinates("[-5, 34]"))

    def test_parse_coordinates_rejects_non_json_and_wrong_shapes(self):
        invalid_responses = (
            "click at 12,34 please",
            '{"x": 12, "y": 34}',
            "[12]",
            "[12, 34, 56]",
            '["12", 34]',
            "[true, 34]",
            "[12, 34",
        )
        for response in invalid_responses:
            with self.subTest(response=response):
                self.assertEqual((-1, -1), parse_coordinates(response))

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
